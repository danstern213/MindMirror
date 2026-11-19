import json
from contextlib import asynccontextmanager

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from conftest import TOKEN
from fake_upstream import BROKEN_ID, LONG_ID, SHORT_ID

pytestmark = pytest.mark.anyio

GUARD = "Searches Dan's personal notes. Only call when the user explicitly asks for personal notes or context."
MISSING_ID = "44444444-4444-4444-4444-444444444444"


@asynccontextmanager
async def session_for(server, token=TOKEN):
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as hc:
        async with streamable_http_client(f"{server.url}/mcp", http_client=hc) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def error_text(result) -> str:
    assert result.is_error, "expected an isError result"
    return result.content[0].text


def rpc(method="tools/list"):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}


# --- auth --------------------------------------------------------------------
async def test_health_is_public(mcp_server):
    r = httpx2.get(f"{mcp_server.url}/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong"},
    {"Authorization": TOKEN},                      # missing the Bearer scheme
    {"Authorization": f"Bearer {TOKEN}x"},
    {"Authorization": f"Basic {TOKEN}"},
])
async def test_mcp_rejects_bad_or_missing_token(mcp_server, headers):
    r = httpx2.post(f"{mcp_server.url}/mcp", json=rpc(), headers={
        "Accept": "application/json, text/event-stream", **headers})
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers
    assert TOKEN not in r.text


async def test_client_with_wrong_token_cannot_initialize(mcp_server):
    with pytest.raises(Exception):
        async with session_for(mcp_server, token="wrong"):
            pass


async def test_unset_token_refuses_everything(make_server):
    server = make_server(MCP_TOKEN="")
    r = httpx2.post(f"{server.url}/mcp", json=rpc(), headers={"Authorization": "Bearer anything"})
    assert r.status_code == 503


async def test_rate_limit_returns_429(make_server):
    server = make_server(RATE_LIMIT_PER_MINUTE="3")
    codes = [httpx2.post(f"{server.url}/mcp", json=rpc()).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


# --- discovery ---------------------------------------------------------------
async def test_exactly_two_tools_with_guarded_descriptions(mcp_server):
    async with session_for(mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    assert sorted(tools) == ["get_note", "search_notes"]
    for tool in tools.values():
        assert tool.description.startswith(GUARD)
    limit = tools["search_notes"].input_schema["properties"]["limit"]
    assert (limit["type"], limit["minimum"], limit["maximum"], limit["default"]) == ("integer", 1, 20, 5)
    assert tools["search_notes"].input_schema["required"] == ["query"]
    assert tools["get_note"].input_schema["required"] == ["id"]


# --- search_notes ------------------------------------------------------------
async def test_search_returns_compact_results_and_forwards_limit(mcp_server, upstream_url):
    async with session_for(mcp_server) as s:
        res = await s.call_tool("search_notes", {"query": "hiking", "limit": 2})
    assert not res.is_error
    out = res.structured_content
    assert out["count"] == 2
    first, second = out["results"]
    assert first == {"id": SHORT_ID, "title": "2026-11-01", "snippet": "Short note about hiking.",
                     "score": 0.912, "date": "2026-11-01"}
    assert len(second["snippet"]) == 301 and second["snippet"].endswith("…")
    assert json.loads(res.content[0].text) == out

    body = [r for r in httpx2.get(f"{upstream_url}/_requests").json() if r["path"] == "/search"][-1]["body"]
    assert body["query"] == "hiking" and body["top_k"] == 2


async def test_search_default_limit_is_5(mcp_server, upstream_url):
    async with session_for(mcp_server) as s:
        await s.call_tool("search_notes", {"query": "defaults"})
    body = [r for r in httpx2.get(f"{upstream_url}/_requests").json() if r["path"] == "/search"][-1]["body"]
    assert body["top_k"] == 5


@pytest.mark.parametrize("args", [
    {"query": "x", "limit": 21}, {"query": "x", "limit": 0}, {"query": ""},
    {"query": "   "}, {"query": "x" * 1001}, {},
])
async def test_search_rejects_bad_input(mcp_server, args):
    async with session_for(mcp_server) as s:
        res = await s.call_tool("search_notes", args)
    assert res.is_error


# --- get_note ----------------------------------------------------------------
async def test_get_note_returns_full_short_note(mcp_server):
    async with session_for(mcp_server) as s:
        res = await s.call_tool("get_note", {"id": SHORT_ID})
    assert not res.is_error
    assert res.structured_content == {
        "id": SHORT_ID, "title": "2026-11-01", "filename": "2026-11-01.md", "date": "2026-11-01",
        "created_at": "2026-11-01T09:00:00", "content": "Short note about hiking.",
        "truncated": False, "total_chars": 24,
    }


async def test_get_note_truncates_long_note_and_says_so(mcp_server):
    async with session_for(mcp_server) as s:
        res = await s.call_tool("get_note", {"id": LONG_ID})
    out = res.structured_content
    assert len(out["content"]) == 8000
    assert out["truncated"] is True and out["total_chars"] == 20000
    assert "8000 of 20000" in out["truncation_note"]


@pytest.mark.parametrize("bad", ["not-a-uuid", "../search", "", "1" * 65])
async def test_get_note_rejects_non_uuid(mcp_server, bad):
    async with session_for(mcp_server) as s:
        res = await s.call_tool("get_note", {"id": bad})
    assert res.is_error


# --- upstream failures -------------------------------------------------------
@pytest.mark.parametrize("tool,args,expected", [
    ("search_notes", {"query": "boom"}, "HTTP 500"),
    ("search_notes", {"query": "slow"}, "did not respond within 1s"),
    ("search_notes", {"query": "notjson"}, "not JSON"),
    ("get_note", {"id": MISSING_ID}, "Note not found"),
    ("get_note", {"id": BROKEN_ID}, "HTTP 500"),
])
async def test_upstream_errors_become_clean_tool_errors(mcp_server, tool, args, expected):
    async with session_for(mcp_server) as s:
        res = await s.call_tool(tool, args)
    text = error_text(res)
    assert expected in text
    assert "Traceback" not in text and "secret" not in text


async def test_upstream_rejecting_key_is_reported(make_server):
    server = make_server(API_KEY="ak_wrong")
    async with session_for(server) as s:
        res = await s.call_tool("search_notes", {"query": "hiking"})
    assert "rejected this server's credentials" in error_text(res)


async def test_unreachable_upstream_is_reported(make_server):
    server = make_server(API_URL="http://127.0.0.1:9/api/v1")
    async with session_for(server) as s:
        res = await s.call_tool("get_note", {"id": SHORT_ID})
    assert "Could not reach" in error_text(res)


# --- logging -----------------------------------------------------------------
async def test_logs_hold_only_tool_status_latency(make_server):
    server = make_server()
    secret_query = "my-very-private-query-zz"
    async with session_for(server) as s:
        await s.call_tool("search_notes", {"query": secret_query})
        await s.call_tool("search_notes", {"query": secret_query, "limit": 99})  # validation error
        await s.call_tool("get_note", {"id": LONG_ID})
        await s.call_tool("get_note", {"id": MISSING_ID})
    logs = server.logs()
    assert "tool=search_notes status=ok latency_ms=" in logs
    assert "tool=get_note status=error latency_ms=" in logs
    for leaked in (secret_query, TOKEN, "ak_test", "hiking", LONG_ID, MISSING_ID, "xxxxxxxx"):
        assert leaked not in logs, f"log leaked {leaked!r}"
