from typing import List, Optional, Dict, Any
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

class SearchService:
    def __init__(self, supabase_client: Optional[Client] = None):
        """Initialize the search service."""
        self.supabase = supabase_client or create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )

    async def search(
        self,
        search_query: SearchQuery,
        api_key: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Perform comprehensive search combining semantic and keyword-based approaches.
        """
        logger.info("=== Starting Comprehensive Search ===")
        logger.info(f"Query: {search_query.query}")
        logger.info(f"User ID: {search_query.user_id}")
        logger.info(f"Requested results: {search_query.top_k}")
        
        # Generate query embedding
        query_embedding = generate_embedding(search_query.query, api_key)
        
        try:
            # Get embeddings and file info with pagination
            all_embeddings = []
            page_size = 1000
            start = 0
            
            while True:
                response = self.supabase.table('embeddings')\
                    .select('*, files!inner(title)')\
                    .eq('user_id', str(search_query.user_id))\
                    .range(start, start + page_size - 1)\
                    .execute()
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"Error fetching embeddings: {response.error}")
                    return []
                
                if not response.data:
                    break
                    
                all_embeddings.extend(response.data)
                logger.info(f"Fetched {len(response.data)} embeddings (total: {len(all_embeddings)})")
                
                if len(response.data) < page_size:
                    break
                    
                start += page_size
                
            embeddings = [
                {
                    'id': item['file_id'],
                    'embedding': json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding'],
                    'text': item['text'],
                    'title': item['files']['title']
                } 
                for item in all_embeddings
            ]
            logger.info(f"Found {len(embeddings)} total embeddings")
            
        except Exception as e:
            logger.error(f"Error fetching embeddings from Supabase: {e}")
            return []

        results: List[SearchResult] = []
        similarity_threshold = 0.75  # Match src implementation
        highly_relevant_threshold = 0.8  # Match src implementation

        # Group results by file_id
        grouped_results: Dict[str, Dict[str, Any]] = {}
        for doc in embeddings:
            score = cosine_similarity(query_embedding, doc['embedding'])
            if score >= similarity_threshold:
                doc_id = doc['id']
                if doc_id not in grouped_results:
                    grouped_results[doc_id] = {
                        'id': doc_id,
                        'score': score,
                        'chunks': [],
                        'title': doc['title']
                    }
                grouped_results[doc_id]['chunks'].append({
                    'text': doc['text'],
                    'score': score
                })

        # Process and combine results
        keywords = extract_keywords(search_query.query)
        
        for doc_id, data in grouped_results.items():
            # Sort chunks by relevance
            sorted_chunks = sorted(data['chunks'], key=lambda x: x['score'], reverse=True)
            # Combine text from more chunks for better context
            # Use up to 5 chunks per document, with higher scores getting more weight
            weighted_chunks = []
            for i, chunk in enumerate(sorted_chunks[:5]):
                weight = 1.0 - (i * 0.15)  # Decrease weight for each subsequent chunk
                weighted_chunks.append({
                    'text': chunk['text'],
                    'weight': weight,
                    'score': chunk['score']
                })
            
            # Combine text with weighting
            combined_text = '\n'.join(
                f"{chunk['text']}" 
                for chunk in weighted_chunks 
                if chunk['score'] >= similarity_threshold
            )
            
            # Calculate keyword score
            keyword_score = calculate_keyword_score(combined_text, keywords)
            matched_keywords = [k for k in keywords if k.lower() in combined_text.lower()]
            
            # Get linked contexts if score is high enough
            linked_contexts = []
            if data['score'] >= highly_relevant_threshold:
                linked_contexts = await get_linked_contexts(combined_text, query_embedding, api_key)
            
            # Keep semantic score as the main score, don't add keyword_score to maintain proper scaling
            results.append(SearchResult(
                id=doc_id,
                score=data['score'],  # Use only semantic score to keep range 0-1
                content=combined_text,
                title=data['title'],
                keyword_score=keyword_score,
                matched_keywords=matched_keywords,
                linked_contexts=linked_contexts
            ))

        # Sort by score and return top 50 results by default
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        return sorted_results[:50]  # Always return up to 50 results for the frontend

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