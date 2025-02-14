from fastapi import Depends, HTTPException, status, Request
from supabase import Client, create_client
from typing import Optional
from uuid import UUID
import logging
import traceback

from .config import get_settings
from ..services.settings_service import SettingsService
from ..services.storage_service import StorageService
from ..services.search_service import SearchService
from ..services.upload_service import UploadService
from ..services.chat_service import ChatService
from ..services.embedding_service import EmbeddingService

settings = get_settings()
logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    try:
        # Create client with minimal options
        return create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_KEY,
            options={
                "auth": {
                    "autoRefreshToken": True,
                    "persistSession": True
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize database connection"
        )

async def get_user_id_from_supabase(request: Request, client: Client = Depends(get_supabase_client)) -> UUID:
    """Get user ID from Supabase session."""
    try:
        # Get the Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )
        
        # Extract the JWT token
        token = auth_header.split(' ')[1]
        
        # Verify the JWT token using Supabase
        user = client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        try:
            # Explicitly convert the string ID to UUID
            return UUID(str(user.user.id))
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid user ID format: {str(e)}"
            )
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )

def get_settings_service(client: Client = Depends(get_supabase_client)) -> SettingsService:
    """Get settings service instance."""
    return SettingsService(client)

def get_storage_service(client: Client = Depends(get_supabase_client)) -> StorageService:
    """Get storage service instance."""
    return StorageService(client)

def get_search_service(client: Client = Depends(get_supabase_client)) -> SearchService:
    """Get search service instance."""
    return SearchService(client)

def get_upload_service(client: Client = Depends(get_supabase_client)) -> UploadService:
    """Get upload service instance."""
    return UploadService(client)

def get_embedding_service(client: Client = Depends(get_supabase_client)) -> EmbeddingService:
    """Get embedding service instance."""
    return EmbeddingService(client)

def get_chat_service(
    client: Client = Depends(get_supabase_client),
    search_service: SearchService = Depends(get_search_service),
    storage_service: StorageService = Depends(get_storage_service)
) -> ChatService:
    """Get chat service instance."""
    return ChatService(client, search_service, storage_service) 