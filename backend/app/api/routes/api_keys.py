"""API routes for managing API keys."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...models.api_key import CreateAPIKeyRequest, CreateAPIKeyResponse, APIKeyInfo
from ...services.api_key_service import APIKeyService
from ...core.deps import get_user_id_from_supabase, get_api_key_service

router = APIRouter()


@router.post("", response_model=CreateAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: APIKeyService = Depends(get_api_key_service)
) -> CreateAPIKeyResponse:
    """
    Create a new API key.

    The returned key will only be shown once - save it securely.
    Requires JWT authentication.
    """
    try:
        result = await service.create_api_key(
            user_id=current_user_id,
            name=request.name,
            expires_in_days=request.expires_in_days
        )
        return CreateAPIKeyResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.get("", response_model=List[APIKeyInfo])
async def list_api_keys(
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: APIKeyService = Depends(get_api_key_service)
) -> List[APIKeyInfo]:
    """
    List all API keys for the current user.

    Returns key metadata without the plaintext key.
    Requires JWT authentication.
    """
    try:
        keys = await service.list_api_keys(current_user_id)
        return [APIKeyInfo(**key) for key in keys]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}"
        )


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: APIKeyService = Depends(get_api_key_service)
) -> dict:
    """
    Revoke an API key.

    The key will no longer be valid for authentication.
    Requires JWT authentication.
    """
    try:
        success = await service.revoke_api_key(key_id, current_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found or already revoked"
            )
        return {"success": True, "message": "API key revoked"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API key: {str(e)}"
        )
