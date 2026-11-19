"""Routes the MCP server calls with an API key: search and GET /files/{id}."""
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import httpx
import pytest

from app.main import app
from app.core import deps
from app.models.file import FileDB

USER = uuid4()
FILE = uuid4()


async def _get(service, path):
    app.dependency_overrides[deps.get_user_id_from_auth] = lambda: USER
    app.dependency_overrides[deps.get_upload_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def teardown_function():
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_file_returns_metadata_and_content():
    record = FileDB(id=FILE, filename="2026-11-01.md", title="2026-11-01", storage_path="p",
                    user_id=USER, status="indexed", document_date=date(2026, 11, 1),
                    created_at=datetime(2026, 11, 1, 9, 0))

    async def get_file_with_content(file_id, user_id):
        assert (file_id, user_id) == (FILE, USER)
        return record, "hello"

    body = (await _get(SimpleNamespace(get_file_with_content=get_file_with_content),
                       f"/api/v1/files/{FILE}")).json()
    assert body == {"id": str(FILE), "title": "2026-11-01", "filename": "2026-11-01.md",
                    "document_date": "2026-11-01", "created_at": "2026-11-01T09:00:00",
                    "content": "hello"}


@pytest.mark.asyncio
async def test_get_file_404_passes_through():
    async def missing(*_):
        raise HTTPException(status_code=404, detail="File not found")

    resp = await _get(SimpleNamespace(get_file_with_content=missing), f"/api/v1/files/{FILE}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_literal_file_routes_still_win_over_the_id_route():
    async def count(*_):
        raise AssertionError("count should not hit get_file_with_content")
    service = SimpleNamespace(get_file_with_content=count, get_user_files=lambda *a, **k: _async([]))
    assert (await _get(service, "/api/v1/files/list")).status_code == 200


def test_search_and_get_file_accept_api_key_auth():
    def dep_of(path, method):
        route = next(r for r in app.routes if getattr(r, "path", None) == path and method in r.methods)
        return [d.call for d in route.dependant.dependencies]
    assert deps.get_user_id_from_auth in dep_of("/api/v1/search", "POST")
    assert deps.get_user_id_from_auth in dep_of("/api/v1/files/{file_id}", "GET")


async def _async(value):
    return value
