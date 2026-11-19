# Big Brain MCP server

A remote MCP server that gives an MCP client (Atlas) read-only access to Dan's notes through the Big Brain backend.

- **Transport:** Streamable HTTP, stateless, single endpoint `POST /mcp`
- **Health:** `GET /health` returns `200 {"status":"ok"}` with no auth
- **Auth:** every other request needs `Authorization: Bearer $MCP_TOKEN`. The token is compared in constant time; anything else gets 401.
- **Rate limit:** `RATE_LIMIT_PER_MINUTE` requests per minute across all callers (default 60), counted before auth. Over the limit returns 429.
- **Logging:** only `tool=<name> status=<ok|error|crash> latency_ms=<n>`. Queries, note text, request bodies and tokens are never logged, and access logs are off.

## Tools

| Tool | Upstream call | Returns |
|---|---|---|
| `search_notes(query: str 1–1000 chars, limit: int 1–20 = 5)` | `POST {API_URL}/search` with `{query, top_k}` | `{count, results: [{id, title, snippet, score, date}]}`. The snippet is the first 300 characters. |
| `get_note(id: UUID str)` | `GET {API_URL}/files/{id}` | `{id, title, filename, date, created_at, content, truncated, total_chars}`. Content is cut at 8,000 characters, with `truncated: true` and a `truncation_note` when that happens. |

Both descriptions begin "Searches Dan's personal notes. Only call when the user explicitly asks for personal notes or context." There are no write tools.

Failures (bad input, upstream 4xx/5xx, timeouts after `UPSTREAM_TIMEOUT_SECONDS`, non-JSON responses) come back as `isError: true` results with a short message. Stack traces and upstream error bodies are never returned.

**Backend requirement:** both upstream routes must accept API-key auth (`X-API-Key`), and `GET /files/{id}` must exist. Both changes ship in this branch under `backend/`. **Deploy the backend before this service**, or every tool call returns "rejected this server's credentials" or "Note not found".

## Environment variables

| Var | Required | Notes |
|---|---|---|
| `API_URL` | yes | Backend base URL including `/api/v1` |
| `API_KEY` | yes | Big Brain app key (`ak_…`), sent upstream as `X-API-Key` |
| `MCP_TOKEN` | yes | Bearer that Atlas must present. `openssl rand -hex 32` |
| `PUBLIC_HOST` | on Railway | This service's public hostname, no scheme. Without it, the SDK's Host check answers every request with 421 behind Railway's proxy |
| `UPSTREAM_TIMEOUT_SECONDS` | no | Default `10` |
| `RATE_LIMIT_PER_MINUTE` | no | Default `60` |

See `.env.example`. Never commit real values (`.env` is gitignored).

## Run and test locally

```bash
cd mcp-server
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -v
```

The tests start a fake upstream (`tests/fake_upstream.py`, whose responses mirror `backend/app/models`) and run the real server as a subprocess. They then drive it with the official MCP client. Coverage: auth rejection, rate limiting, both tools, input validation, upstream errors (500, timeout, non-JSON, 404, bad key, unreachable), truncation, and a check that logs leak nothing.

## Deploy on Railway

1. Merge this branch to `main` so the backend picks up the API-key routes (Railway auto-deploys the backend from `main`).
2. In the Railway project, create a new service from this repo with **Root Directory** `mcp-server`. It builds with Nixpacks on Python 3.12 and starts with `railway.toml`'s command. The health check is `/health`.
3. Under **Settings → Networking**, generate a public domain, e.g. `big-brain-mcp.up.railway.app`.
4. Set the variables `API_URL`, `API_KEY`, `MCP_TOKEN`, and `PUBLIC_HOST=<that domain>`.
5. Smoke test the deployed URL:

   ```bash
   MCP_TOKEN=... .venv/bin/python smoke_test.py https://<domain> --query "hiking"
   ```

   It checks `/health`, checks that `/mcp` rejects a missing token, then runs `initialize → tools/list → tools/call search_notes → tools/call get_note`. It prints only counts and ids and exits non-zero on any failure.
6. In Atlas, add the server URL `https://<domain>/mcp` with header `Authorization: Bearer <MCP_TOKEN>`.
