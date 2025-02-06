from fastapi import APIRouter, Depends, HTTPException
from typing import List
from uuid import UUID
import logging

from ...services.embedding_service import EmbeddingService
from ...models.file import EmbeddingDB
from ...core.deps import get_user_id_from_supabase, get_embedding_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/file/{file_id}",
    response_model=List[EmbeddingDB],
    response_model_exclude_none=True
)
async def get_file_embeddings(
    file_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Get all embeddings for a specific file.
    
    This endpoint is useful for:
    1. Debugging embedding generation
    2. Verifying file processing status
    3. Advanced semantic analysis
    """
    try:
        result = await service.get_embeddings_by_file_id(str(file_id))
        logger.info(f"Raw response data: {result}")
        return result
    except Exception as e:
        logger.error(f"Error fetching embeddings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching embeddings: {str(e)}"
        )

@router.post(
    "/generate",
    response_model=List[EmbeddingDB],
    response_model_exclude_none=True
)
async def generate_embeddings(
    text: str,
    file_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Generate embeddings for a given text.
    
    This endpoint allows:
    1. Manual embedding generation
    2. Reprocessing failed embeddings
    3. Testing embedding configuration
    """
    try:
        return await service.generate_and_save_embedding(
            text=text,
            file_id=str(file_id),
            user_id=str(current_user_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating embeddings: {str(e)}"
        ) 