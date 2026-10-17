"""
MCP server for the Big Brain notes API.

Exposes the AI Note Copilot REST API as MCP tools so an external agent can read
Dan's notes alongside its own context. This is the validation spike: one tool,
`list_notes`, wrapping GET /files/list — the endpoint that already accepts API
key auth on the deployed backend.

Two transports are mounted so either kind of client can connect:
  POST /mcp   streamable HTTP (current standard)
  GET  /sse   HTTP+SSE (deprecated, for older clients)
Both serve the same tools. /health is public; everything else needs the bearer.
"""
import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx2
from pydantic import Field
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("big-brain-mcp")

# --- Configuration -----------------------------------------------------------
# Outbound: how we authenticate to the Big Brain backend. Single-user, same
# posture as the Telegram bridge — one API key, one user id, held in env.
API_URL = os.environ.get(
    "CHAT_API_URL", "https://mindmirror-production.up.railway.app/api/v1"
).rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
USER_ID = os.environ.get("USER_ID", "")

# Inbound: the shared secret a calling agent must present.
MCP_BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")

# This service's own public hostname on Railway, e.g. big-brain-mcp.up.railway.app.
# Needed because the SDK's DNS-rebinding guard checks the Host header, which
# behind Railway's proxy is the public domain rather than 127.0.0.1.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()
# Escape hatch: if the calling client sends a Host or Origin the guard rejects,
# set this to 1 to turn the guard off without a code change.
DISABLE_HOST_CHECK = os.environ.get("DISABLE_DNS_REBINDING_PROTECTION", "") == "1"

HTTP_TIMEOUT = httpx2.Timeout(10.0, read=60.0)


def _backend_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY, "Accept": "application/json"}


# --- Server ------------------------------------------------------------------
mcp = MCPServer(
    name="big-brain-notes",
    version="0.1.0",
    instructions=(
        "Dan's personal note archive — daily notes, journals, meeting notes and "
        "work reflections going back years, imported from Roam and Obsidian. "
        "Use these tools to ground answers in what Dan has actually written and "
        "experienced before, rather than guessing."
    ),
)


@mcp.tool(
    name="list_notes",
    description=(
        "List notes in Dan's personal archive, most recently uploaded first. "
        "Returns titles and dates only, not note contents — use it to see what is "
        "in the archive, check coverage for a time period, or confirm a note exists. "
        "This does NOT search note text."
    ),
)
async def list_notes(
    limit: Annotated[
        int,
        Field(
            description="How many notes to return, most recent first. 1-100.",
            ge=1,
            le=100,
        ),
    ] = 20,
) -> dict[str, Any]:
    """List the most recently uploaded notes."""
    if not API_KEY or not USER_ID:
        return {"error": "Server is misconfigured: API_KEY or USER_ID is not set."}

    limit = max(1, min(int(limit), 100))

    async with httpx2.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            # `limit` is sent as a query param for the newer backend that supports
            # it; the currently deployed build ignores unknown params and returns
            # everything, so the slice below is what actually enforces the cap.
            resp = await client.get(
                f"{API_URL}/files/list",
                headers=_backend_headers(),
                params={"limit": limit},
            )
        except httpx2.RequestError as e:
            logger.error("Backend unreachable: %s", e)
            return {"error": f"Could not reach the notes backend: {e}"}

    if resp.status_code == 401:
        return {"error": "The notes backend rejected the API key (401)."}
    if resp.status_code >= 400:
        return {"error": f"The notes backend returned {resp.status_code}."}

    try:
        rows = resp.json()
    except ValueError:
        return {"error": "The notes backend returned a response that was not JSON."}

    if not isinstance(rows, list):
        return {"error": "Unexpected response shape from the notes backend."}

    notes = [
        {
            "id": row.get("id"),
            "title": row.get("title") or row.get("filename"),
            "filename": row.get("filename"),
            "note_date": row.get("document_date"),
            "uploaded_at": row.get("created_at"),
            "indexing_status": row.get("status"),
        }
        for row in rows[:limit]
    ]

    return {
        "returned": len(notes),
        "total_in_archive": len(rows),
        "notes": notes,
    }


# --- Inbound auth ------------------------------------------------------------
class BearerAuthMiddleware:
    """Require `Authorization: Bearer <token>` on everything but public_paths.

    Written as raw ASGI rather than BaseHTTPMiddleware on purpose: both
    transports stream responses, and BaseHTTPMiddleware buffers them.
    """

    def __init__(self, app: Any, token: str, public_paths: frozenset[str]) -> None:
        self.app = app
        self.token = token
        self.public_paths = public_paths

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        # Lifespan and websocket scopes pass straight through.
        if scope["type"] != "http" or scope.get("path", "") in self.public_paths:
            await self.app(scope, receive, send)
            return

        if not self.token:
            await self._deny(
                scope, receive, send,
                "This server has no MCP_BEARER_TOKEN configured, so it refuses all requests.",
                status=503,
            )
            return

        headers = dict(scope.get("headers") or [])
        presented = headers.get(b"authorization", b"").decode("latin-1")
        # Constant-time compare so the token can't be recovered by timing.
        if not hmac.compare_digest(presented, f"Bearer {self.token}"):
            await self._deny(scope, receive, send, "Missing or invalid bearer token.")
            return

        await self.app(scope, receive, send)

    async def _deny(
        self, scope: Any, receive: Any, send: Any, detail: str, status: int = 401
    ) -> None:
        response = JSONResponse(
            {"error": detail},
            status_code=status,
            headers={"WWW-Authenticate": 'Bearer realm="big-brain-mcp"'} if status == 401 else None,
        )
        await response(scope, receive, send)


async def health(_request: Request) -> JSONResponse:
    """Public health check — also tells you which env vars are still missing."""
    missing = [
        name
        for name, value in (
            ("API_KEY", API_KEY),
            ("USER_ID", USER_ID),
            ("MCP_BEARER_TOKEN", MCP_BEARER_TOKEN),
        )
        if not value
    ]
    return JSONResponse(
        {
            "status": "healthy" if not missing else "unconfigured",
            "backend": API_URL,
            "missing_config": missing,
            "transports": {"streamable_http": "/mcp", "sse": "/sse"},
            "dns_rebinding_protection": bool(PUBLIC_HOST) and not DISABLE_HOST_CHECK,
        }
    )


def _transport_security() -> TransportSecuritySettings:
    if DISABLE_HOST_CHECK or not PUBLIC_HOST:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=False, allowed_hosts=[], allowed_origins=[]
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
        allowed_origins=[f"https://{PUBLIC_HOST}"],
    )


def build_app() -> Any:
    security = _transport_security()

    # Each of these returns its own Starlette app. We take their routes and serve
    # them from one app so a single Railway service answers both transports.
    streamable = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,  # safe behind a proxy and across replicas
        transport_security=security,
        host=PUBLIC_HOST or "127.0.0.1",
    )
    sse = mcp.sse_app(
        sse_path="/sse",
        message_path="/messages/",
        transport_security=security,
        host=PUBLIC_HOST or "127.0.0.1",
    )

    # The streamable transport needs its session manager running for the life of
    # the process. Delegating to the sub-app's own lifespan means we don't have to
    # reimplement whatever the SDK set up.
    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with streamable.router.lifespan_context(streamable):
            logger.info("MCP server ready — backend=%s", API_URL)
            yield

    inner = Starlette(
        routes=[Route("/health", health, methods=["GET"]), *streamable.routes, *sse.routes],
        lifespan=lifespan,
    )
    return BearerAuthMiddleware(
        inner, token=MCP_BEARER_TOKEN, public_paths=frozenset({"/health"})
    )


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
