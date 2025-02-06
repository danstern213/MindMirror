from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from uuid import UUID

from ...services.storage_service import StorageService
from ...core.deps import get_user_id_from_supabase, get_storage_service

router = APIRouter()

@router.get("/embeddings/{embedding_id}")
async def get_embedding(
    embedding_id: str,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: StorageService = Depends(get_storage_service)
) -> Dict[str, Any]:
    """Get a specific embedding by ID."""
    result = await service.get_embedding(embedding_id)
    if not result:
        raise HTTPException(status_code=404, detail="Embedding not found")
    return result

@router.get("/embeddings/user/{user_id}")
async def get_user_embeddings(
    user_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: StorageService = Depends(get_storage_service)
) -> List[Dict[str, Any]]:
    """Get all embeddings for a specific user."""
    # Ensure user can only access their own embeddings
    if user_id != current_user_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access other user's embeddings"
        )
    return await service.get_user_embeddings(user_id)

@router.delete("/embeddings/{embedding_id}")
async def delete_embedding(
    embedding_id: str,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: StorageService = Depends(get_storage_service)
) -> Dict[str, bool]:
    """Delete a specific embedding."""
    success = await service.delete_embedding(embedding_id)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete embedding completely"
        )
    return {"success": True} 