"""Fake Big Brain backend for tests. Shapes copied from backend/app/models."""
import asyncio
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

API_KEY = os.environ.get("FAKE_API_KEY", "ak_test")
SHORT_ID = "11111111-1111-1111-1111-111111111111"
LONG_ID = "22222222-2222-2222-2222-222222222222"
BROKEN_ID = "33333333-3333-3333-3333-333333333333"
LONG_TEXT = "x" * 20000

NOTES = {
    SHORT_ID: {"id": SHORT_ID, "title": "2026-11-01", "filename": "2026-11-01.md",
               "document_date": "2026-11-01", "created_at": "2026-11-01T09:00:00",
               "content": "Short note about hiking."},
    LONG_ID: {"id": LONG_ID, "title": "Long", "filename": "Long.md", "document_date": None,
              "created_at": "2026-10-01T09:00:00", "content": LONG_TEXT},
}

# Every request the fake received, for assertions. Exposed at GET /_requests.
received: list[dict] = []


def _authed(request: Request) -> bool:
    return request.headers.get("x-api-key") == API_KEY


async def search(request: Request):
    body = await request.json()
    received.append({"path": "/search", "body": body})
    if not _authed(request):
        return JSONResponse({"detail": "Invalid or expired API key"}, status_code=401)
    q = body["query"]
    if q == "boom":
        return JSONResponse({"detail": "Traceback (most recent call last): secret"}, status_code=500)
    if q == "slow":
        await asyncio.sleep(5)
    if q == "notjson":
        return PlainTextResponse("<html>Bad gateway</html>")
    rows = [
        {"id": SHORT_ID, "score": 0.91234, "content": "Short   note\nabout hiking.", "title": "2026-11-01",
         "explicit": None, "document_date": "2026-11-01"},
        {"id": LONG_ID, "score": 0.5, "content": LONG_TEXT, "title": "Long", "document_date": None},
    ]
    return JSONResponse(rows[: body.get("top_k", 200)])


async def get_file(request: Request):
    file_id = request.path_params["file_id"]
    received.append({"path": f"/files/{file_id}"})
    if not _authed(request):
        return JSONResponse({"detail": "Invalid or expired API key"}, status_code=401)
    if file_id == BROKEN_ID:
        return JSONResponse({"detail": "Error fetching file"}, status_code=500)
    if file_id not in NOTES:
        return JSONResponse({"detail": "File not found"}, status_code=404)
    return JSONResponse(NOTES[file_id])


async def requests_seen(_request: Request):
    return JSONResponse(received)


app = Starlette(routes=[
    Route("/api/v1/search", search, methods=["POST"]),
    Route("/api/v1/files/{file_id}", get_file, methods=["GET"]),
    Route("/_requests", requests_seen, methods=["GET"]),
])
