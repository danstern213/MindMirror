from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.search import SearchQuery
from app.services import search_service as search_module
from app.services.chat_service import ChatService
from app.services.embedding_helper import _embedding_kwargs, embedding_input
from app.services.search_service import SearchService, _group_chunks_by_document


def chunk(file_id, index, score, text=None, title="Note.md"):
    return {
        "file_id": file_id, "chunk_index": index, "score": score,
        "text": text or f"chunk {index}", "title": title, "document_date": None,
    }


def test_document_scores_as_its_best_chunk_regardless_of_order():
    a, b = str(uuid4()), str(uuid4())
    # Note A's weak chunk arrives first; the old loop scored A by it.
    chunks = [chunk(a, 0, 0.40, title="A.md"), chunk(b, 0, 0.60, title="B.md"), chunk(a, 3, 0.80, title="A.md")]

    results = sorted(_group_chunks_by_document(chunks, []), key=lambda r: r.score, reverse=True)

    assert [r.title for r in results] == ["A.md", "B.md"]
    assert results[0].score == 0.80


def test_document_content_is_top_chunks_in_reading_order():
    doc = str(uuid4())
    chunks = [chunk(doc, i, score) for i, score in [(4, 0.9), (0, 0.5), (2, 0.7)]]

    [result] = _group_chunks_by_document(chunks, [])

    assert result.content == "chunk 0\nchunk 2\nchunk 4"


def test_document_keeps_at_most_five_best_chunks():
    doc = str(uuid4())
    chunks = [chunk(doc, i, i / 10) for i in range(8)]

    [result] = _group_chunks_by_document(chunks, [])

    assert result.content.split("\n") == [f"chunk {i}" for i in range(3, 8)]


def test_embedding_input_prefixes_title_and_date():
    assert embedding_input("body", "2025-03-14.md", date(2025, 3, 14)) == "2025-03-14 (2025-03-14)\n\nbody"
    assert embedding_input("body", "Temple.md", None) == "Temple\n\nbody"
    assert embedding_input("body", None, None) == "body"


def test_dimensions_only_sent_to_text_embedding_3_models():
    assert _embedding_kwargs("text-embedding-3-large") == {"model": "text-embedding-3-large", "dimensions": 1536}
    assert _embedding_kwargs("text-embedding-ada-002") == {"model": "text-embedding-ada-002"}


@pytest.mark.asyncio
async def test_search_falls_back_to_legacy_scan_when_rpc_is_missing(monkeypatch):
    service = SearchService(MagicMock())
    doc = str(uuid4())
    service._vector_search_chunks = AsyncMock(side_effect=Exception("function match_embeddings does not exist"))
    service._legacy_scan_chunks = MagicMock(return_value=[chunk(doc, 0, 0.8, title="Legacy.md")])

    results = await service.search(SearchQuery(query="q", user_id=uuid4()))

    assert [r.title for r in results] == ["Legacy.md"]


@pytest.mark.asyncio
async def test_search_uses_vector_results_without_touching_legacy():
    service = SearchService(MagicMock())
    service._vector_search_chunks = AsyncMock(return_value=[chunk(str(uuid4()), 0, 0.5, title="Vec.md")])
    service._legacy_scan_chunks = MagicMock()

    results = await service.search(SearchQuery(query="q", user_id=uuid4()))

    assert [r.title for r in results] == ["Vec.md"]
    service._legacy_scan_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_linked_note_matches_with_or_without_extension_and_is_whole():
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value.in_.return_value.eq.return_value
    query.execute.return_value = SimpleNamespace(data=[{
        "id": str(uuid4()), "title": "Temple.md", "document_date": None,
        "embeddings": [{"text": "second", "chunk_index": 1}, {"text": "first", "chunk_index": 0}],
    }])

    result = await SearchService(supabase).search_by_title("Temple", "user")

    supabase.table.return_value.select.return_value.in_.assert_called_with("title", ["Temple", "Temple.md"])
    assert result.content == "first\nsecond"
    assert result.explicit


def _chat_service(openai_response=None, openai_error=None):
    service = ChatService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    create = AsyncMock(side_effect=openai_error, return_value=openai_response)
    service.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return service


@pytest.mark.asyncio
async def test_follow_up_is_rewritten_into_standalone_query():
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Serena marriage feedback"))])
    service = _chat_service(openai_response=reply)

    query = await service._standalone_search_query("what else did she say?", [{"role": "user", "content": "marriage feedback from Serena"}])

    assert query == "Serena marriage feedback"


@pytest.mark.asyncio
async def test_query_rewrite_failure_falls_back_to_raw_message():
    service = _chat_service(openai_error=Exception("rate limited"))

    query = await service._standalone_search_query("what else?", [{"role": "user", "content": "x"}])

    assert query == "what else?"
