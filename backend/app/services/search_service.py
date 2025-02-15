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
                response = self.supabase.table('embeddings')\
                    .select('*, files!inner(title)')\
                    .eq('user_id', str(search_query.user_id))\
                    .limit(page_size)\
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
                        if doc_id not in grouped_results:
                            grouped_results[doc_id] = {
                                'id': doc_id,
                                'score': score,
                                'chunks': [],
                                'title': item['files']['title']
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
                
                results.append(SearchResult(
                    id=doc_id,
                    score=data['score'],
                    content=combined_text,
                    title=data['title'],
                    keyword_score=keyword_score,
                    matched_keywords=matched_keywords,
                    linked_contexts=linked_contexts
                ))
            
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