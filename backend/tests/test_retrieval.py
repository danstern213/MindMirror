from datetime import date
from pathlib import Path
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
    service._vector_search_chunks = AsyncMock(side_effect=Exception("function match_embeddings(vector, text) does not exist"))
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
async def test_search_timeout_does_not_fall_back_to_slow_legacy_scan():
    service = SearchService(MagicMock())
    service._vector_search_chunks = AsyncMock(side_effect=Exception("canceling statement due to statement timeout"))
    service._legacy_scan_chunks = MagicMock()

    results = await service.search(SearchQuery(query="q", user_id=uuid4()))

    assert results == []
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


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.mark.asyncio
async def test_follow_up_is_rewritten_into_standalone_query():
    service = _chat_service(openai_response=_reply('{"query": "Serena marriage feedback", "start": null, "end": null}'))

    plan = await service._plan_search("what else did she say?", [{"role": "user", "content": "marriage feedback from Serena"}])

    assert plan.query == "Serena marriage feedback"
    assert plan.date_start is None


@pytest.mark.asyncio
async def test_plan_failure_falls_back_to_the_date_parser():
    service = _chat_service(openai_error=Exception("rate limited"))

    plan = await service._plan_search("what was I doing in March 2025", [])

    assert (plan.date_start, plan.date_end) == (date(2025, 3, 1), date(2025, 3, 31))
    assert "march" not in plan.query.lower()


@pytest.mark.asyncio
async def test_plan_failure_without_dates_keeps_the_raw_message():
    service = _chat_service(openai_error=Exception("rate limited"))

    plan = await service._plan_search("what else?", [{"role": "user", "content": "x"}])

    assert plan.query == "what else?"


@pytest.mark.asyncio
async def test_period_the_parser_cannot_read_comes_from_the_model():
    service = _chat_service(openai_response=_reply(
        '{"query": "what I was doing", "start": "2026-03-01", "end": "2026-05-31", "period": "spring 2026"}'))

    plan = await service._plan_search("what was I up to last spring?", [], today=date(2026, 11, 1))

    assert (plan.date_start, plan.date_end, plan.period) == (date(2026, 3, 1), date(2026, 5, 31), "spring 2026")


@pytest.mark.asyncio
async def test_plain_first_question_skips_the_planner():
    service = _chat_service(openai_error=AssertionError("planner should not run"))

    plan = await service._plan_search("how do I handle setbacks?", [])

    assert plan.query == "how do I handle setbacks?"
    assert plan.date_start is None


def test_search_plan_parsing_tolerates_bad_model_output():
    from app.services.chat_service import _parse_search_plan
    today = date(2026, 11, 1)

    assert _parse_search_plan("not json", today) is None
    assert _parse_search_plan('{"query": ""}', today) is None
    # A garbled date drops the range but keeps the query.
    plan = _parse_search_plan('{"query": "q", "start": "March", "end": "2025-03-31"}', today)
    assert plan.query == "q" and plan.date_start is None
    # Reversed dates are swapped; an open end runs to today.
    assert _parse_search_plan('{"query": "q", "start": "2025-03-31", "end": "2025-03-01"}', today).date_start == date(2025, 3, 1)
    assert _parse_search_plan('{"query": "q", "start": "2025-06-01", "end": null}', today).date_end == today
    assert _parse_search_plan('```json\n{"query": "q"}\n```', today).query == "q"


def test_stitch_chunks_removes_the_overlap_between_chunks():
    from app.services.search_service import stitch_chunks
    text = "".join(f"sentence number {i}. " for i in range(200))
    chunks = [text[0:1500], text[1200:2700], text[2400:]]

    assert stitch_chunks(chunks) == text


def test_stitch_chunks_falls_back_to_newline_when_no_overlap():
    from app.services.search_service import stitch_chunks
    assert stitch_chunks(["first part of the note", "an unrelated second part"]) == \
        "first part of the note\nan unrelated second part"


@pytest.mark.asyncio
async def test_recent_notes_keep_newest_within_budget_in_reading_order():
    supabase = MagicMock()
    files_query = supabase.table.return_value.select.return_value.eq.return_value

    def note(day, chars, title):
        return {"id": str(uuid4()), "title": title, "document_date": f"2026-10-{day:02d}",
                "created_at": "2026-10-31T00:00:00", "embeddings": [{"text": "x" * chars, "chunk_index": 0}]}

    files_query.gte.return_value.execute.return_value = SimpleNamespace(data=[
        note(5, 400, "old.md"), note(20, 400, "mid.md"), note(28, 400, "new.md"),
    ])
    files_query.is_.return_value.gte.return_value.execute.return_value = SimpleNamespace(data=[])

    # Budget of 250 tokens (~1000 chars) fits two 400-char notes: the two newest.
    notes = await SearchService(supabase).get_recent_notes(uuid4(), days=30, token_budget=250, today=date(2026, 10, 31))

    assert [n.title for n in notes] == ["mid.md", "new.md"]


def _range_supabase(files):
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value
    query.execute.return_value = SimpleNamespace(data=files)
    return supabase


IDS = {}


def _file(day, chars, title):
    return {"id": IDS.setdefault(title, str(uuid4())), "title": title, "document_date": f"2025-03-{day:02d}",
            "created_at": "2025-03-31T00:00:00", "embeddings": [{"text": "x" * chars, "chunk_index": 0}]}


@pytest.mark.asyncio
async def test_range_notes_are_whole_and_in_date_order():
    supabase = _range_supabase([_file(20, 100, "c.md"), _file(2, 100, "a.md"), _file(9, 100, "b.md"), _file(15, 0, "blank.md")])

    notes, total = await SearchService(supabase).get_notes_in_range(
        uuid4(), date(2025, 3, 1), date(2025, 3, 31), token_budget=10_000)

    assert [n.title for n in notes] == ["a.md", "b.md", "c.md"]
    assert total == 3  # blank pages do not count


@pytest.mark.asyncio
async def test_range_over_budget_keeps_what_search_ranked_first():
    supabase = _range_supabase([_file(d, 400, f"{d}.md") for d in (1, 10, 20, 30)])

    # Room for two 400-char notes; search ranked the 10th, then the 1st.
    notes, total = await SearchService(supabase).get_notes_in_range(
        uuid4(), date(2025, 3, 1), date(2025, 3, 31), token_budget=200, ranked_ids=[IDS["10.md"], IDS["1.md"]])

    assert [n.title for n in notes] == ["1.md", "10.md"]
    assert total == 4


def test_front_matter_created_date_is_read():
    from app.services.date_extraction_service import DateExtractionService
    ex = DateExtractionService()

    found = ex.extract_date_from_frontmatter("---\ncreated: 2022-08-18 08:39:03\nupdated: 2024-01-01\n---\nBezos on Day 1")

    assert found.date == date(2022, 8, 18) and found.source == "frontmatter"
    assert ex.extract_date_from_frontmatter("no header\ncreated: 2022-08-18") is None
    assert ex.extract_date_from_frontmatter("---\ncreated: 2022-13-45\n---") is None


def test_sync_reuploads_only_notes_edited_after_upload(tmp_path):
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from sync_new_roam import edited_since

    note = tmp_path / "2026-10-30.md"
    note.write_text("written later")
    os.utime(note, (1_790_000_000, 1_790_000_000))  # 2026-09-20 UTC

    assert edited_since(note, "2026-09-01T08:00:00+00:00")
    assert not edited_since(note, "2026-10-01T08:00:00Z")
    assert not edited_since(note, "2026-10-01T08:00:00")  # naive timestamps are UTC
    assert not edited_since(note, None)


def test_backfill_matches_both_daily_note_spellings_and_dropped_punctuation():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from backfill_missing_notes import name_key, name_keys, note_body

    assert name_key("September 1st, 2021.md") in name_keys("2021-09-01.md")
    assert name_key("Am I a good husband?.md") in name_keys("Am I a good husband.md")
    assert note_body("---\ncreated: 2022-08-18\n---\nhello") == "hello"


def test_chunking_keeps_the_whole_note_when_paragraph_breaks_come_early():
    from app.services.embedding_service import EmbeddingService
    # One early paragraph break, then 4,000 characters of single-newline lines:
    # the old chunker cut ~250-char chunks here and dropped everything after.
    text = "First paragraph about Samara.\n\n" + "".join(f"line {i} of the long entry.\n" for i in range(160))

    chunks = EmbeddingService(MagicMock()).chunk_text(text, chunk_size=2000, overlap=300)

    assert "line 159 of the long entry." in chunks[-1]
    assert all(len(c) >= 900 for c in chunks[:-1])
    assert from_search_stitch(chunks) == text.strip()


def from_search_stitch(chunks):
    from app.services.search_service import stitch_chunks
    return stitch_chunks(chunks)
