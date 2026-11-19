"""
Smoke test: initialize -> tools/list -> tools/call against a running server.

Usage:
    export MCP_TOKEN=...
    python smoke_test.py https://<your-service>.up.railway.app [--query "text"]

Also checks /health and that /mcp rejects a missing token. Exits non-zero on
any failure. Prints counts and ids only, never note text.
"""
import argparse
import asyncio
import os
import sys

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f' - {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


async def run(base: str, token: str, query: str) -> None:
    async with httpx2.AsyncClient(timeout=30) as hc:
        r = await hc.get(f"{base}/health")
        check(r.status_code == 200, "GET /health", str(r.status_code))
        r = await hc.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        check(r.status_code == 401, "POST /mcp without token is rejected", str(r.status_code))

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=60)) as hc:
        async with streamable_http_client(f"{base}/mcp", http_client=hc) as (read, write, *_):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                check(True, "initialize", f"{init.server_info.name} {init.server_info.version}, "
                                          f"protocol {init.protocol_version}")

                names = sorted(t.name for t in (await session.list_tools()).tools)
                check(names == ["get_note", "search_notes"], "tools/list", str(names))

                res = await session.call_tool("search_notes", {"query": query, "limit": 3})
                hits = (res.structured_content or {}).get("results", [])
                detail = res.content[0].text[:200] if res.is_error and res.content else f"{len(hits)} results"
                check(not res.is_error, "tools/call search_notes", detail)

                if hits:
                    res = await session.call_tool("get_note", {"id": hits[0]["id"]})
                    note = res.structured_content or {}
                    detail = (res.content[0].text[:200] if res.is_error and res.content
                              else f"id={note.get('id')} chars={note.get('total_chars')} "
                                   f"truncated={note.get('truncated')}")
                    check(not res.is_error, "tools/call get_note", detail)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("url", help="Server base URL, e.g. https://x.up.railway.app")
    p.add_argument("--query", default="what have I been working on lately")
    args = p.parse_args()
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        sys.exit("Set MCP_TOKEN first.")
    base = args.url.rstrip("/")
    print(f"Smoke testing {base}")
    asyncio.run(run(base, token, args.query))
    print("\nALL PASSED" if not failures else f"\nFAILED: {', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
