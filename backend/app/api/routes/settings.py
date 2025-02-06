from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from uuid import UUID

from ...services.settings_service import SettingsService
from ...core.deps import get_settings_service, get_user_id_from_supabase

router = APIRouter()

@router.get("")
async def get_settings(
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: SettingsService = Depends(get_settings_service)
) -> Dict[str, Any]:
    """Get current user's settings."""
    settings = await service.get_user_settings(current_user_id)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    return settings

@router.patch("")
async def update_settings(
    settings_update: Dict[str, Any],
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: SettingsService = Depends(get_settings_service)
) -> Dict[str, Any]:
    """Update user settings."""
    updated_settings = await service.update_user_settings(current_user_id, settings_update)
    if not updated_settings:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )
    return updated_settings 