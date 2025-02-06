from fastapi import APIRouter, Depends
from typing import List
from uuid import UUID

from ...services.search_service import SearchService
from ...models.search import SearchQuery, SearchResult
from ...core.deps import get_user_id_from_supabase, get_search_service

router = APIRouter()

@router.post("", response_model=List[SearchResult])
async def search(
    query: SearchQuery,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: SearchService = Depends(get_search_service)
) -> List[SearchResult]:
    """
    Perform a comprehensive search across user's documents.
    
    The search combines:
    1. Semantic similarity using embeddings
    2. Keyword-based relevance scoring
    3. Context linking for highly relevant results
    """
    # Ensure the user_id in the query matches the authenticated user
    query.user_id = current_user_id
    return await service.search(query)

@router.post("/semantic", response_model=List[SearchResult])
async def semantic_search(
    query: str,
    top_k: int = 3,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: SearchService = Depends(get_search_service)
) -> List[SearchResult]:
    """
    Perform a purely semantic search without keyword matching.
    
    This endpoint is useful when you want to find conceptually similar content
    without considering exact keyword matches.
    """
    return await service.perform_semantic_search(
        query=query,
        user_id=str(current_user_id),
        top_k=top_k
    ) 