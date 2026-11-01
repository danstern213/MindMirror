from typing import List, Optional, Dict, Any, Set, Sequence, Tuple
from datetime import date, timedelta
from uuid import UUID
from supabase import Client, create_client
import asyncio
import json
import logging
from .embedding_helper import generate_embedding_async, generate_embedding
from .search_helper import (
    cosine_similarity,
    extract_keywords,
    calculate_keyword_score
)
from ..models.search import SearchResult, SearchQuery
from ..core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Date boost configuration
DATE_BOOST_WITHIN_RANGE = 0.15  # Boost for documents within the date range
DATE_BOOST_NEAR_RANGE = 0.08  # Boost for documents within 7 days of range
DATE_BOOST_DECAY_DAYS = 30  # Days over which date boost decays to zero
DATE_MATCH_SCORE = 0.95  # Score for date-matched results (high but allows semantic to rank higher)

VECTOR_MATCH_COUNT = 150  # Chunks pulled from pgvector per query, before grouping by note
MAX_CHUNKS_PER_DOCUMENT = 5
LEGACY_SIMILARITY_THRESHOLD = 0.75  # ada-002 scale; text-embedding-3 scores run much lower
EXPLICIT_NOTE_MAX_CHARS = 40000  # ~10K tokens, so one huge linked note cannot crowd out everything else

class SearchService:
    def __init__(self, supabase_client: Optional[Client] = None):
        """Initialize the search service."""
        self.supabase = supabase_client or create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )

    def _calculate_date_boost(
        self,
        document_date: Optional[date],
        date_start: Optional[date],
        date_end: Optional[date]
    ) -> float:
        """
        Calculate a score boost based on how well a document's date matches the query range.

        Args:
            document_date: The date of the document (may be None)
            date_start: Start of the query date range
            date_end: End of the query date range

        Returns:
            A boost value between 0 and DATE_BOOST_WITHIN_RANGE
        """
        if not document_date or not date_start or not date_end:
            return 0.0

        # Document is within the date range - full boost
        if date_start <= document_date <= date_end:
            return DATE_BOOST_WITHIN_RANGE

        # Calculate distance from range
        if document_date < date_start:
            days_away = (date_start - document_date).days
        else:
            days_away = (document_date - date_end).days

        # Within a week of the range - partial boost
        if days_away <= 7:
            return DATE_BOOST_NEAR_RANGE

        # Decaying boost up to DATE_BOOST_DECAY_DAYS away
        if days_away <= DATE_BOOST_DECAY_DAYS:
            decay_factor = 1 - (days_away / DATE_BOOST_DECAY_DAYS)
            return DATE_BOOST_NEAR_RANGE * decay_factor * 0.5

        return 0.0

    def _parse_document_date(self, date_value: Any) -> Optional[date]:
        """Parse a document date from various formats."""
        if date_value is None:
            return None
        if isinstance(date_value, date):
            return date_value
        if isinstance(date_value, str):
            try:
                return date.fromisoformat(date_value)
            except ValueError:
                return None
        return None

    async def get_date_matched_files(
        self,
        user_id: UUID,
        date_start: date,
        date_end: date,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Retrieve documents by date range to supplement semantic search.

        These results are ADDED to semantic results, not replacing them.
        This ensures that date-specific queries return all content from that date
        even if it doesn't semantically match the query text.

        Args:
            user_id: The user's ID
            date_start: Start of the date range
            date_end: End of the date range
            limit: Maximum number of results to return

        Returns:
            List of SearchResult objects for documents within the date range
        """
        try:
            logger.info(f"Fetching date-matched files from {date_start} to {date_end}")

            response = self.supabase.table('files')\
                .select('id, title, document_date, embeddings(text)')\
                .eq('user_id', str(user_id))\
                .gte('document_date', date_start.isoformat())\
                .lte('document_date', date_end.isoformat())\
                .order('document_date', desc=True)\
                .limit(limit)\
                .execute()

            if hasattr(response, 'error') and response.error:
                logger.error(f"Error fetching date-matched files: {response.error}")
                return []

            results = []
            for file in response.data:
                # Combine all embedding chunks for this file
                embeddings = file.get('embeddings', [])
                content = '\n'.join(e['text'] for e in embeddings if e.get('text'))

                if not content:
                    continue

                doc_date = self._parse_document_date(file.get('document_date'))

                results.append(SearchResult(
                    id=file['id'],
                    score=DATE_MATCH_SCORE,  # High score but not 1.0 - semantic matches can still rank higher
                    content=content,
                    title=file['title'],
                    document_date=doc_date
                ))

            logger.info(f"Found {len(results)} date-matched files")
            return results

        except Exception as e:
            logger.error(f"Error fetching date-matched files: {e}")
            return []

    async def search(
        self,
        search_query: SearchQuery,
        api_key: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Perform comprehensive search combining semantic and keyword-based approaches.

        For temporal queries (with date_start/date_end), this method:
        1. Fetches date-matched documents directly (ensures all content from that date is returned)
        2. Runs semantic search (existing functionality)
        3. Combines results, with date-matched docs filling gaps where semantic similarity was too low
        """
        logger.info("=== Starting Comprehensive Search ===")
        logger.info(f"Query: {search_query.query}")
        logger.info(f"User ID: {search_query.user_id}")
        logger.info(f"Requested results: {search_query.top_k}")
        if search_query.date_start or search_query.date_end:
            logger.info(f"Date range: {search_query.date_start} to {search_query.date_end}")

        # For temporal queries, first fetch date-matched documents
        # These are ADDED to semantic results, not replacing them
        date_matched_results: List[SearchResult] = []
        date_matched_ids: Set[str] = set()

        if search_query.date_start and search_query.date_end:
            date_matched_results = await self.get_date_matched_files(
                search_query.user_id,
                search_query.date_start,
                search_query.date_end
            )
            date_matched_ids = {str(r.id) for r in date_matched_results}
            logger.info(f"Pre-fetched {len(date_matched_results)} date-matched documents")

        try:
            chunks = await self._vector_search_chunks(search_query, api_key)
        except Exception as e:
            # Fall back only when the function does not exist. The legacy scan
            # takes ~90s on this corpus, so using it for a timeout or a blip
            # turns a slow answer into a useless one; answer from recent notes
            # and explicit links instead.
            if 'match_embeddings' in str(e) and ('does not exist' in str(e) or 'PGRST202' in str(e)):
                logger.warning(f"match_embeddings missing, falling back to legacy scan: {e}")
                chunks = await asyncio.to_thread(self._legacy_scan_chunks, search_query, api_key)
            else:
                logger.error(f"pgvector search failed: {e}")
                chunks = []

        keywords = extract_keywords(search_query.query)
        results = _group_chunks_by_document(chunks, keywords)

        for result in results:
            date_boost = self._calculate_date_boost(
                result.document_date, search_query.date_start, search_query.date_end
            )
            result.score = min(1.0, result.score + date_boost)

        # Add date-matched documents the semantic search missed, so a query about
        # a specific day returns that day's notes even when they score low.
        semantic_result_ids = {str(r.id) for r in results}
        added_date_matches = 0
        for date_result in date_matched_results:
            if str(date_result.id) not in semantic_result_ids:
                results.append(date_result)
                added_date_matches += 1
        if added_date_matches > 0:
            logger.info(f"Added {added_date_matches} date-matched documents not found by semantic search")

        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        logger.info(f"Found {len(sorted_results)} relevant documents")
        return sorted_results[:50]

    async def _vector_search_chunks(
        self,
        search_query: SearchQuery,
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Top chunks by cosine similarity, scored inside Postgres (match_embeddings)."""
        query_embedding = await generate_embedding_async(search_query.query, api_key)
        params = {
            'query_embedding': query_embedding,
            'match_user_id': str(search_query.user_id),
            'match_count': VECTOR_MATCH_COUNT,
            'date_start': search_query.date_start.isoformat() if search_query.date_start else None,
            'date_end': search_query.date_end.isoformat() if search_query.date_end else None,
        }
        # The Supabase client is synchronous; keep it off the event loop.
        response = await asyncio.to_thread(
            lambda: self.supabase.rpc('match_embeddings', params).execute()
        )
        return [
            {
                'file_id': row['file_id'],
                'chunk_index': row.get('chunk_index'),
                'text': row['text'],
                'score': row['similarity'],
                'title': row['title'],
                'document_date': self._parse_document_date(row.get('document_date')),
            }
            for row in response.data or []
        ]

    def _legacy_scan_chunks(
        self,
        search_query: SearchQuery,
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Pre-pgvector search: download every ada-002 vector and score it in Python.

        Slow (about a second per 1,000 chunks) and blocking, so it runs in a
        worker thread. Kept only as a fallback until the backfill has run; delete
        it, and the JSON `embedding` column, once the pgvector path is proven.
        """
        query_embedding = generate_embedding(search_query.query, api_key, model=settings.LEGACY_EMBEDDING_MODEL)
        chunks: List[Dict[str, Any]] = []
        offset = 0
        page_size = 500
        while True:
            query = self.supabase.table('embeddings')\
                .select('file_id, chunk_index, text, embedding, files!inner(title, document_date)')\
                .eq('user_id', str(search_query.user_id))
            if search_query.date_start:
                query = query.gte('files.document_date', search_query.date_start.isoformat())
            if search_query.date_end:
                query = query.lte('files.document_date', search_query.date_end.isoformat())
            rows = query.limit(page_size).offset(offset).execute().data
            if not rows:
                break
            for item in rows:
                embedding = json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding']
                score = cosine_similarity(query_embedding, embedding)
                if score >= LEGACY_SIMILARITY_THRESHOLD:
                    chunks.append({
                        'file_id': item['file_id'],
                        'chunk_index': item.get('chunk_index'),
                        'text': item['text'],
                        'score': score,
                        'title': item['files']['title'],
                        'document_date': self._parse_document_date(item['files'].get('document_date')),
                    })
            if len(rows) < page_size:
                break
            offset += page_size
        return chunks

    async def get_recent_notes(
        self,
        user_id: UUID,
        days: int,
        token_budget: int,
        today: Optional[date] = None
    ) -> List[SearchResult]:
        """
        The user's notes from the last `days`, whole, oldest first, newest kept
        when they do not all fit in `token_budget`.

        This is what is on the user's mind right now, and it goes into every
        chat prompt as-is rather than through search: at ~30K tokens a month it
        fits, and search only ever returns fragments of it. A note's date is its
        document_date (from the filename); undated notes count by upload date.
        """
        since = ((today or date.today()) - timedelta(days=days)).isoformat()
        columns = 'id, title, document_date, created_at, embeddings(text, chunk_index)'

        def fetch():
            dated = self.supabase.table('files').select(columns)\
                .eq('user_id', str(user_id))\
                .gte('document_date', since)\
                .execute().data or []
            undated = self.supabase.table('files').select(columns)\
                .eq('user_id', str(user_id))\
                .is_('document_date', 'null')\
                .gte('created_at', since)\
                .execute().data or []
            return dated + undated

        try:
            files = await asyncio.to_thread(fetch)
        except Exception as e:
            logger.error(f"Error fetching recent notes: {e}")
            return []

        notes = self._whole_notes(files)
        # Newest first while filling the budget, then back to reading order.
        notes.sort(key=lambda n: n.document_date or date.min, reverse=True)
        kept, used = _fill_budget(notes, token_budget)
        kept.sort(key=lambda n: n.document_date or date.min)
        logger.info(f"Recent notes: kept {len(kept)} of {len(notes)} from the last {days} days (~{used} tokens)")
        return kept

    async def get_notes_in_range(
        self,
        user_id: UUID,
        date_start: date,
        date_end: date,
        token_budget: int,
        ranked_ids: Sequence[str] = ()
    ) -> Tuple[List[SearchResult], int]:
        """
        Every note dated within the range, whole and oldest first, plus how
        many notes the range holds in all.

        For "what was I doing in March 2025" the answer is that month's notes,
        not the few fragments that happen to resemble "what was I doing". When
        they do not all fit, the ones search ranked highest (`ranked_ids`) go
        in first, then the rest newest first.
        """
        columns = 'id, title, document_date, created_at, embeddings(text, chunk_index)'

        def fetch():
            return self.supabase.table('files').select(columns)\
                .eq('user_id', str(user_id))\
                .gte('document_date', date_start.isoformat())\
                .lte('document_date', date_end.isoformat())\
                .execute().data or []

        try:
            files = await asyncio.to_thread(fetch)
        except Exception as e:
            logger.error(f"Error fetching notes from {date_start} to {date_end}: {e}")
            return [], 0

        notes = self._whole_notes(files)
        rank = {str(note_id): i for i, note_id in enumerate(ranked_ids)}
        notes.sort(key=lambda n: (rank.get(str(n.id), len(rank)), -(n.document_date or date.min).toordinal()))
        kept, used = _fill_budget(notes, token_budget)
        kept.sort(key=lambda n: n.document_date or date.min)
        logger.info(f"Notes {date_start}..{date_end}: kept {len(kept)} of {len(notes)} (~{used} tokens)")
        return kept, len(notes)

    def _whole_notes(self, files: List[Dict[str, Any]]) -> List[SearchResult]:
        """Files with their embedded chunks joined back into the full note; blank ones dropped."""
        notes = []
        for file in files:
            chunks = sorted(file.get('embeddings') or [], key=lambda e: e.get('chunk_index') or 0)
            content = stitch_chunks([c['text'] for c in chunks if c.get('text')])
            if not content.strip():
                continue
            note_date = self._parse_document_date(file.get('document_date')) \
                or self._parse_document_date((file.get('created_at') or '')[:10])
            notes.append(SearchResult(id=file['id'], score=1.0, content=content,
                                      title=file['title'], document_date=note_date))
        return notes

    async def search_by_title(self, title: str, user_id: str) -> Optional[SearchResult]:
        """
        Load a note the user linked as [[title]], in full and in reading order.

        Titles are stored with their extension ("Note.md") but people link both
        ways, so either spelling matches.
        """
        base = title.strip().removesuffix('.md')
        try:
            response = self.supabase.table('files')\
                .select('id, title, document_date, embeddings(text, chunk_index)')\
                .in_('title', [base, f"{base}.md"])\
                .eq('user_id', user_id)\
                .execute()

            if not response.data:
                return None

            file = response.data[0]
            chunks = sorted(file.get('embeddings') or [], key=lambda e: e.get('chunk_index') or 0)
            content = stitch_chunks([c['text'] for c in chunks if c.get('text')])
            if len(content) > EXPLICIT_NOTE_MAX_CHARS:
                content = content[:EXPLICIT_NOTE_MAX_CHARS] + "\n[...note truncated...]"

            return SearchResult(
                id=file['id'],
                score=1.0,  # Maximum relevance for exact title match
                content=content,
                title=file['title'],
                explicit=True,
                full_content=content,
                document_date=self._parse_document_date(file.get('document_date'))
            )
        except Exception as e:
            logger.error(f"Error searching by title: {e}")
            return None


def _fill_budget(notes: List[SearchResult], token_budget: int) -> Tuple[List[SearchResult], int]:
    """Take notes in the given order while they fit; a long one is skipped, not a stop."""
    kept, used = [], 0
    for note in notes:
        cost = len(note.content) // 4
        if used + cost > token_budget:
            continue
        kept.append(note)
        used += cost
    return kept, used


def stitch_chunks(texts: List[str], max_overlap: int = 600) -> str:
    """
    Rejoin a note's chunks into its original text.

    Chunks overlap by CHUNK_OVERLAP characters, so a plain join repeats every
    seam. Where the end of one chunk reappears at the start of the next, drop
    the repeat; otherwise fall back to a newline join.
    """
    if not texts:
        return ""
    out = texts[0]
    for nxt in texts[1:]:
        overlap = 0
        for k in range(min(max_overlap, len(out), len(nxt)), 20, -1):
            if out.endswith(nxt[:k]):
                overlap = k
                break
        out = out + nxt[overlap:] if overlap else out + "\n" + nxt
    return out


def _group_chunks_by_document(chunks: List[Dict[str, Any]], keywords: List[str]) -> List[SearchResult]:
    """
    Collapse chunk hits into one result per note.

    A note scores as its BEST chunk. (The old loop kept whichever chunk the
    database happened to return first, so ranking between notes was close to
    arbitrary.) Its content is its top chunks, put back in reading order.
    """
    by_doc: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        by_doc.setdefault(str(chunk['file_id']), []).append(chunk)

    results = []
    for doc_id, doc_chunks in by_doc.items():
        top = sorted(doc_chunks, key=lambda c: c['score'], reverse=True)[:MAX_CHUNKS_PER_DOCUMENT]
        in_order = sorted(top, key=lambda c: c.get('chunk_index') or 0)
        combined_text = '\n'.join(c['text'] for c in in_order)
        results.append(SearchResult(
            id=doc_id,
            score=top[0]['score'],
            content=combined_text,
            title=top[0]['title'],
            # Shown to the model as context only; not used for ranking until
            # the retrieval eval shows it helps.
            keyword_score=calculate_keyword_score(combined_text, keywords),
            matched_keywords=[k for k in keywords if k.lower() in combined_text.lower()],
            document_date=top[0].get('document_date'),
        ))
    return results
