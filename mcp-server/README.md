# Big Brain MCP server

Exposes the AI Note Copilot API over the Model Context Protocol so an external
agent can read your notes alongside its own context.

This is the **validation spike**: one tool, `list_notes`, wrapping
`GET /files/list` — the endpoint that already accepts API-key auth on the
deployed backend. The point is to prove the integration works with your
third-party agent service *before* investing in the pgvector migration that
real search needs.

## Why this is a separate service

`mcp` 2.x requires `pydantic>=2.12` and `httpx2`. The backend pins
`pydantic==2.6.1` and `httpx<0.25` (forced by `supabase==2.3.0`). Mounting MCP
into the backend would mean upgrading Supabase and Pydantic in production.
A sibling service keeps both on current dependencies — same pattern as
`telegram-bridge`.

## Endpoints

| Path | Purpose |
|---|---|
| `POST /mcp` | Streamable HTTP transport (current standard) |
| `GET /sse` | HTTP+SSE transport (deprecated, for older clients) |
| `GET /health` | Public health check; lists any missing config |

Both transports serve the same tools, so you can try whichever one your agent
service speaks. `/health` is the only unauthenticated route.

## Configuration

Copy `.env.example` to `.env` for local work, or set these as Railway variables.

| Variable | Notes |
|---|---|
| `CHAT_API_URL` | Backend base URL, default is the Railway production one |
| `API_KEY` | Big Brain API key (`ak_…`) — the same one the Telegram bridge uses |
| `USER_ID` | Your Supabase user UUID |
| `MCP_BEARER_TOKEN` | The secret calling agents must present. `openssl rand -hex 32` |
| `PUBLIC_HOST` | **Required in production.** This service's hostname, no scheme |
| `DISABLE_DNS_REBINDING_PROTECTION` | Set to `1` only as an escape hatch (see below) |

### The `PUBLIC_HOST` gotcha

The SDK has a DNS-rebinding guard that validates the `Host` header. Behind
Railway's proxy that header is your public domain, not `127.0.0.1`, so if you
leave `PUBLIC_HOST` unset in production the guard has nothing to match and every
MCP request fails with **421 Invalid Host header**. Set it to
`your-service.up.railway.app`.

If your agent service sends a `Host` or `Origin` the guard still rejects, set
`DISABLE_DNS_REBINDING_PROTECTION=1` to turn the guard off without a code
change. Bearer auth is unaffected either way.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in API_KEY, USER_ID, MCP_BEARER_TOKEN
set -a; source .env; set +a
uvicorn server:app --host 127.0.0.1 --port 8000
```

Then, in another shell:

```bash
MCP_BEARER_TOKEN=<your token> python smoke_test.py http://127.0.0.1:8000
```

`smoke_test.py` runs the handshake, tool discovery and a real tool call over
**both** transports, and checks that the bearer gate rejects bad tokens. It
exits non-zero on failure, and works against the deployed URL too.

## Deploy to Railway

1. New service in the same project, root directory `mcp-server/`.
2. Set `API_KEY`, `USER_ID`, `MCP_BEARER_TOKEN`.
3. Deploy once to get the public domain, then set `PUBLIC_HOST` to that
   hostname and redeploy.
4. Verify:

```bash
curl https://<your-host>/health
```

5. End-to-end:

```bash
MCP_BEARER_TOKEN=<your token> python smoke_test.py https://<your-host>
```

## Point an agent at it

Most hosts want the URL plus a header. For Claude Code:

```bash
claude mcp add --transport http big-brain https://<your-host>/mcp --header "Authorization: Bearer <your token>"
```

For another agent service, give it `https://<your-host>/mcp` and the
`Authorization: Bearer <token>` header. If it only supports the older
transport, point it at `https://<your-host>/sse` instead.

## What this deliberately does not do yet

`search_notes` and `get_note` are the tools that make the "where else have I
faced this?" use case work, and they are **not here on purpose**:

- `POST /search` and `GET /files/{id}/content` are still JWT-only on the
  backend. Both need their dependency changed from
  `get_user_id_from_supabase` to `get_user_id_from_auth`.
- Search currently pages every embedding row out of Supabase and computes
  cosine similarity in pure Python, with no pgvector. One query is tolerable;
  the 5–10 queries per turn that analogical retrieval needs will time out.

So: confirm the connector works with this spike first. Then do the pgvector
migration and the `text-embedding-3-large` re-embed in one pass, and add the
search tools on top.
