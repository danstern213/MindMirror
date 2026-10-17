"""
Smoke test for the Big Brain MCP server.

Drives the server the way a real MCP client will: handshake, tool discovery and
a tool call, over BOTH transports, plus a check that the bearer gate actually
rejects unauthenticated callers.

Usage:
    export MCP_BEARER_TOKEN=...
    python smoke_test.py                                  # defaults to localhost:8000
    python smoke_test.py http://127.0.0.1:8901
    python smoke_test.py https://your-mcp.up.railway.app   # after deploying

Exits non-zero if any check fails.
"""
import asyncio
import json
import os
import sys

import httpx2
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


async def exercise(session: ClientSession, transport: str) -> None:
    init = await session.initialize()
    check(
        init.server_info.name == "big-brain-notes",
        f"[{transport}] handshake",
        f"{init.server_info.name} v{init.server_info.version}, protocol {init.protocol_version}",
    )

    tools = await session.list_tools()
    names = [t.name for t in tools.tools]
    check("list_notes" in names, f"[{transport}] tool discovery", f"tools={names}")

    result = await session.call_tool("list_notes", {"limit": 3})
    payload = result.structured_content or {}
    if result.is_error:
        text = result.content[0].text if result.content else "<no content>"
        check(False, f"[{transport}] list_notes call", text[:160])
        return
    if "error" in payload:
        # The protocol round-trip worked; the backend call did not.
        check(False, f"[{transport}] list_notes reached backend", str(payload["error"])[:160])
        return
    check(
        isinstance(payload.get("notes"), list),
        f"[{transport}] list_notes call",
        f"returned {payload.get('returned')} of {payload.get('total_in_archive')} notes",
    )
    if payload.get("notes"):
        print(f"         first note: {json.dumps(payload['notes'][0])}")


async def main() -> None:
    if not TOKEN:
        print("MCP_BEARER_TOKEN is not set — set it to the server's token and re-run.")
        sys.exit(2)

    print(f"Testing {BASE}\n")

    print("Public + auth gate")
    async with httpx2.AsyncClient(timeout=30) as hc:
        r = await hc.get(f"{BASE}/health")
        check(r.status_code == 200, "/health is public", f"{r.status_code} {r.text[:120]}")

        r = await hc.post(f"{BASE}/mcp", json={}, headers={"Accept": "application/json, text/event-stream"})
        check(r.status_code == 401, "/mcp rejects a request with no token", f"got {r.status_code}")

        r = await hc.post(
            f"{BASE}/mcp",
            json={},
            headers={"Authorization": "Bearer wrong-token", "Accept": "application/json, text/event-stream"},
        )
        check(r.status_code == 401, "/mcp rejects a wrong token", f"got {r.status_code}")

    print("\nStreamable HTTP  (POST /mcp)")
    try:
        async with httpx2.AsyncClient(headers=HEADERS, timeout=60) as hc:
            async with streamable_http_client(f"{BASE}/mcp", http_client=hc) as (read, write):
                async with ClientSession(read, write) as session:
                    await exercise(session, "streamable")
    except Exception as e:
        check(False, "[streamable] transport", f"{type(e).__name__}: {e}")

    print("\nHTTP + SSE  (GET /sse)")
    try:
        async with sse_client(f"{BASE}/sse", headers=HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await exercise(session, "sse")
    except Exception as e:
        check(False, "[sse] transport", f"{type(e).__name__}: {e}")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
