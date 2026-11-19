"""
Remote MCP server for Dan's notes (Big Brain backend).

Two read-only tools over Streamable HTTP at POST /mcp (stateless):
  search_notes  -> POST {API_URL}/search
  get_note      -> GET  {API_URL}/files/{id}

GET /health is public. Everything else needs `Authorization: Bearer $MCP_TOKEN`
and is rate limited. Logs carry only tool name, status and latency: never
queries, note text, request bodies or tokens.
"""
import hmac
import logging
import os
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from functools import wraps
from typing import Annotated, Any

import httpx2
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("big-brain-mcp")
# The SDK logs tool failures (validation messages echo the arguments) and the
# HTTP client logs URLs. Keep both quiet so no query or note id reaches the logs.
for noisy in ("mcp", "httpx2", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# --- Configuration (env only) ------------------------------------------------
API_URL = os.environ.get("API_URL", "https://mindmirror-production.up.railway.app/api/v1").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")          # Big Brain app key (ak_...), sent as X-API-Key
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")      # what Atlas must present as the bearer
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()  # e.g. big-brain-mcp.up.railway.app
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "10"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

MAX_NOTE_CHARS = 8000
SNIPPET_CHARS = 300
MAX_QUERY_CHARS = 1000
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# The backend's SearchQuery model requires a user_id field but overwrites it with
# the user the API key belongs to, so any well-formed UUID works here.
PLACEHOLDER_USER_ID = "00000000-0000-0000-0000-000000000000"

TOOL_GUARD = "Searches Dan's personal notes. Only call when the user explicitly asks for personal notes or context."

mcp = MCPServer(name="big-brain-notes", version="1.0.0")


# --- Upstream ----------------------------------------------------------------
async def _upstream(method: str, path: str, **kwargs: Any) -> Any:
    """Call the backend; turn every failure into a ToolError with a plain message."""
    if not API_KEY:
        raise ToolError("Server misconfigured: API_KEY is not set.")
    headers = {"X-API-Key": API_KEY, "Accept": "application/json"}
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(UPSTREAM_TIMEOUT)) as client:
            resp = await client.request(method, f"{API_URL}{path}", headers=headers, **kwargs)
    except httpx2.TimeoutException:
        raise ToolError(f"The notes backend did not respond within {UPSTREAM_TIMEOUT:g}s.") from None
    except httpx2.RequestError:
        raise ToolError("Could not reach the notes backend.") from None

    if resp.status_code == 404:
        raise ToolError("Note not found.")
    if resp.status_code in (401, 403):
        raise ToolError("The notes backend rejected this server's credentials.")
    if resp.status_code >= 400:
        raise ToolError(f"The notes backend returned an error (HTTP {resp.status_code}).")
    try:
        return resp.json()
    except ValueError:
        raise ToolError("The notes backend returned a response that was not JSON.") from None


def logged(fn):
    """Log tool name, outcome and latency. Nothing about arguments or results."""
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        status = "ok"
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            status = "error"
            raise
        except Exception:
            status = "crash"
            raise
        finally:
            ms = (time.perf_counter() - start) * 1000
            logger.info("tool=%s status=%s latency_ms=%.0f", fn.__name__, status, ms)
    return wrapper


# --- Tools -------------------------------------------------------------------
@mcp.tool(
    name="search_notes",
    description=(
        f"{TOOL_GUARD} Semantic search over the notes. Returns up to `limit` matches, best first, "
        "each with id, title, snippet (first ~300 characters of the matched text), score (0-1 relevance) "
        "and date (YYYY-MM-DD, or null). Use get_note with a result's id for the full text."
    ),
)
@logged
async def search_notes(
    query: Annotated[str, Field(description="What to look for, in natural language. String, 1-1000 characters.",
                                min_length=1, max_length=MAX_QUERY_CHARS)],
    limit: Annotated[int, Field(description="Maximum number of results. Integer 1-20, default 5.",
                                ge=1, le=20)] = 5,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ToolError("query must not be blank.")

    rows = await _upstream("POST", "/search", json={
        "query": query, "top_k": limit, "user_id": PLACEHOLDER_USER_ID,
    })
    if not isinstance(rows, list):
        raise ToolError("Unexpected response shape from the notes backend.")

    results = []
    for row in rows[:limit]:
        text = " ".join(str(row.get("content") or "").split())
        results.append({
            "id": row.get("id"),
            "title": row.get("title"),
            "snippet": text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else ""),
            "score": round(float(row.get("score") or 0), 3),
            "date": row.get("document_date"),
        })
    return {"count": len(results), "results": results}


@mcp.tool(
    name="get_note",
    description=(
        f"{TOOL_GUARD} Fetch one note by id. Returns id, title, filename, date, created_at and "
        f"content. Content over {MAX_NOTE_CHARS} characters is cut to the first {MAX_NOTE_CHARS}; "
        "then `truncated` is true and `total_chars` gives the full length."
    ),
)
@logged
async def get_note(
    id: Annotated[str, Field(description="The note's id: a UUID string, as returned by search_notes.",
                             max_length=64)],
) -> dict[str, Any]:
    id = id.strip()
    if not UUID_RE.match(id):
        raise ToolError("id must be a UUID, as returned by search_notes.")

    note = await _upstream("GET", f"/files/{id}")
    if not isinstance(note, dict):
        raise ToolError("Unexpected response shape from the notes backend.")

    content = str(note.get("content") or "")
    truncated = len(content) > MAX_NOTE_CHARS
    result = {
        "id": note.get("id"),
        "title": note.get("title"),
        "filename": note.get("filename"),
        "date": note.get("document_date"),
        "created_at": note.get("created_at"),
        "content": content[:MAX_NOTE_CHARS],
        "truncated": truncated,
        "total_chars": len(content),
    }
    if truncated:
        result["truncation_note"] = (
            f"Note truncated: showing the first {MAX_NOTE_CHARS} of {len(content)} characters."
        )
    return result


# --- Inbound auth + rate limit ----------------------------------------------
class GateMiddleware:
    """Bearer auth (constant-time) and a global sliding-window rate limit.

    Raw ASGI on purpose: BaseHTTPMiddleware buffers streamed responses.
    """

    def __init__(self, app: Any, token: str, per_minute: int, public_paths: frozenset[str]) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode() if token else b""
        self.per_minute = per_minute
        self.public_paths = public_paths
        self.hits: deque[float] = deque()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path", "") in self.public_paths:
            await self.app(scope, receive, send)
            return

        if not self.expected:
            await self._reply(scope, receive, send, 503, "Server misconfigured: MCP_TOKEN is not set.")
            return

        # Counted before auth, so guessing tokens is throttled too.
        now = time.monotonic()
        while self.hits and now - self.hits[0] > 60:
            self.hits.popleft()
        if len(self.hits) >= self.per_minute:
            await self._reply(scope, receive, send, 429, "Rate limit exceeded. Try again shortly.",
                              {"Retry-After": "60"})
            return
        self.hits.append(now)

        presented = dict(scope.get("headers") or []).get(b"authorization", b"")
        if not hmac.compare_digest(presented, self.expected):
            await self._reply(scope, receive, send, 401, "Missing or invalid bearer token.",
                              {"WWW-Authenticate": 'Bearer realm="big-brain-mcp"'})
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reply(scope, receive, send, status: int, detail: str, headers: dict | None = None) -> None:
        await JSONResponse({"error": detail}, status_code=status, headers=headers)(scope, receive, send)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _transport_security() -> TransportSecuritySettings:
    # The SDK checks Host against this list. Behind Railway's proxy, Host is the
    # public domain, so without PUBLIC_HOST set there every request gets a 421.
    if not PUBLIC_HOST:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False,
                                         allowed_hosts=[], allowed_origins=[])
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
        allowed_origins=[f"https://{PUBLIC_HOST}"],
    )


def build_app() -> Any:
    streamable = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=_transport_security(),
        host=PUBLIC_HOST or "127.0.0.1",
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with streamable.router.lifespan_context(streamable):
            logger.info("ready upstream=%s", API_URL)
            yield

    inner = Starlette(routes=[Route("/health", health, methods=["GET"]), *streamable.routes],
                      lifespan=lifespan)
    return GateMiddleware(inner, token=MCP_TOKEN, per_minute=RATE_LIMIT_PER_MINUTE,
                          public_paths=frozenset({"/health"}))


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), access_log=False)
