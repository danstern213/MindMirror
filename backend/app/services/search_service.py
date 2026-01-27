from typing import List, Optional, Dict, Any, Set
from datetime import date, timedelta
from uuid import UUID
from supabase import Client, create_client
import json
import logging
from .embedding_helper import generate_embedding
from .search_helper import (
    cosine_similarity,
    extract_keywords,
    calculate_keyword_score,
    get_linked_contexts
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

        # Generate query embedding
        query_embedding = generate_embedding(search_query.query, api_key)

        # Initialize constants
        similarity_threshold = 0.75  # Match src implementation
        highly_relevant_threshold = 0.8  # Match src implementation
        page_size = 500  # Reduced batch size for memory efficiency

        try:
            # Process embeddings in batches and maintain only the top results
            grouped_results: Dict[str, Dict[str, Any]] = {}
            offset = 0
            
            while True:
                logger.info(f"Fetching batch at offset {offset}")
                query = self.supabase.table('embeddings')\
                    .select('*, files!inner(title, document_date)')\
                    .eq('user_id', str(search_query.user_id))

                # Apply date filtering if specified
                if search_query.date_start:
                    query = query.gte('files.document_date', search_query.date_start.isoformat())
                if search_query.date_end:
                    query = query.lte('files.document_date', search_query.date_end.isoformat())

                response = query.limit(page_size)\
                    .offset(offset)\
                    .execute()
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"Error fetching embeddings: {response.error}")
                    return []
                
                if not response.data:
                    break
                
                batch_size = len(response.data)
                logger.info(f"Processing batch of {batch_size} embeddings")
                
                # Process each embedding in the batch
                for item in response.data:
                    embedding = json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding']
                    score = cosine_similarity(query_embedding, embedding)

                    if score >= similarity_threshold:
                        doc_id = item['file_id']
                        # Parse document date
                        doc_date = self._parse_document_date(item['files'].get('document_date'))

                        if doc_id not in grouped_results:
                            grouped_results[doc_id] = {
                                'id': doc_id,
                                'score': score,
                                'chunks': [],
                                'title': item['files']['title'],
                                'document_date': doc_date
                            }
                        # Only keep the top 5 chunks per document
                        if len(grouped_results[doc_id]['chunks']) < 5:
                            grouped_results[doc_id]['chunks'].append({
                                'text': item['text'],
                                'score': score
                            })
                        else:
                            # Replace lower scoring chunk if this one is better
                            min_chunk = min(grouped_results[doc_id]['chunks'], key=lambda x: x['score'])
                            if score > min_chunk['score']:
                                grouped_results[doc_id]['chunks'].remove(min_chunk)
                                grouped_results[doc_id]['chunks'].append({
                                    'text': item['text'],
                                    'score': score
                                })
                
                if batch_size < page_size:
                    break
                    
                offset += page_size
            
            logger.info(f"Found {len(grouped_results)} relevant documents")
            
            # Extract keywords once for all documents
            keywords = extract_keywords(search_query.query)
            results: List[SearchResult] = []
            
            # Process each document's results
            for doc_id, data in grouped_results.items():
                # Sort chunks by score
                sorted_chunks = sorted(data['chunks'], key=lambda x: x['score'], reverse=True)

                # Combine text from chunks
                combined_text = '\n'.join(chunk['text'] for chunk in sorted_chunks)

                # Calculate keyword score
                keyword_score = calculate_keyword_score(combined_text, keywords)
                matched_keywords = [k for k in keywords if k.lower() in combined_text.lower()]

                # Get linked contexts only for highly relevant results
                linked_contexts = []
                if data['score'] >= highly_relevant_threshold:
                    linked_contexts = await get_linked_contexts(combined_text, query_embedding, api_key)

                # Calculate date boost if temporal query
                date_boost = self._calculate_date_boost(
                    data.get('document_date'),
                    search_query.date_start,
                    search_query.date_end
                )
                boosted_score = min(1.0, data['score'] + date_boost)

                if date_boost > 0:
                    logger.debug(f"Applied date boost {date_boost:.3f} to {data['title']} (date: {data.get('document_date')})")

                results.append(SearchResult(
                    id=doc_id,
                    score=boosted_score,
                    content=combined_text,
                    title=data['title'],
                    keyword_score=keyword_score,
                    matched_keywords=matched_keywords,
                    linked_contexts=linked_contexts,
                    document_date=data.get('document_date')
                ))

            # Combine date-matched results with semantic results
            # Add date-matched documents that weren't found by semantic search
            # This ensures temporal queries return ALL content from that date
            semantic_result_ids = {str(r.id) for r in results}
            added_date_matches = 0

            for date_result in date_matched_results:
                if str(date_result.id) not in semantic_result_ids:
                    results.append(date_result)
                    added_date_matches += 1

            if added_date_matches > 0:
                logger.info(f"Added {added_date_matches} date-matched documents not found by semantic search")

            # Sort and return top results
            sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
            return sorted_results[:50]
            
        except Exception as e:
            logger.error(f"Error fetching embeddings from Supabase: {e}")
            return []

    async def search_by_title(self, title: str, user_id: str) -> Optional[SearchResult]:
        """Search for a file by its exact title."""
        try:
            # Query the files table for an exact title match
            response = self.supabase.table('files')\
                .select('*, embeddings(text)')\
                .eq('title', title)\
                .eq('user_id', user_id)\
                .execute()
            
            if not response.data:
                return None
            
            file = response.data[0]
            content = file['embeddings'][0]['text'] if file.get('embeddings') else ""
            
            return SearchResult(
                id=file['id'],
                score=1.0,  # Maximum relevance for exact title match
                content=content,
                title=title,
                explicit=True,
                full_content=content
            )
        except Exception as e:
            logger.error(f"Error searching by title: {e}")
            return None 