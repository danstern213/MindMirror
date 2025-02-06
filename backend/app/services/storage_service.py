from typing import List, Optional, Dict, Any
import aiofiles
import json
import os
from pathlib import Path
from uuid import UUID
from supabase import Client, create_client
import logging

from ..core.config import get_settings
from ..models.file import EmbeddingDB

settings = get_settings()
logger = logging.getLogger(__name__)

class StorageService:
    """
    Storage service for managing embeddings with local backup functionality.
    Provides fallback mechanism if Supabase is unavailable.
    """
    
    def __init__(
        self,
        supabase_client: Optional[Client] = None,
        storage_dir: Optional[str] = None
    ):
        self.supabase = supabase_client or create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        self.storage_dir = Path(storage_dir or "embeddings_backup")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, embedding_id: str) -> Path:
        """Get the file path for an embedding ID."""
        safe_id = str(embedding_id).replace('/', '_').replace('\\', '_')
        return self.storage_dir / f"{safe_id}.json"
    
    async def save_embedding_backup(self, embedding: Dict[str, Any]) -> None:
        """Save embedding to local backup storage."""
        file_path = self._get_file_path(embedding['id'])
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(json.dumps(embedding))
    
    async def get_embedding_backup(self, embedding_id: str) -> Optional[Dict[str, Any]]:
        """Get embedding from local backup storage."""
        file_path = self._get_file_path(embedding_id)
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return None
    
    async def save_embedding(self, embedding: Dict[str, Any]) -> Optional[EmbeddingDB]:
        """Save embedding to Supabase and local backup."""
        try:
            # Save to Supabase
            response = self.supabase.table('embeddings').insert(embedding).execute()
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error saving to Supabase: {response.error}")
                # Save to backup and return None
                await self.save_embedding_backup(embedding)
                return None
            
            # Save to backup storage
            await self.save_embedding_backup(embedding)
            
            return EmbeddingDB(**response.data[0])
            
        except Exception as e:
            logger.error(f"Error saving embedding: {e}")
            # Save to backup
            await self.save_embedding_backup(embedding)
            return None
    
    async def get_embedding(self, embedding_id: str) -> Optional[Dict[str, Any]]:
        """Get embedding from Supabase or fall back to local storage."""
        try:
            # Try Supabase first
            response = self.supabase.table('embeddings')\
                .select('*')\
                .eq('id', embedding_id)\
                .single()\
                .execute()
            
            if response.data:
                return response.data
                
        except Exception as e:
            logger.error(f"Error getting embedding from Supabase: {e}")
        
        # Fall back to local storage
        return await self.get_embedding_backup(embedding_id)
    
    async def get_user_embeddings(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get all embeddings for a specific user."""
        try:
            # Try Supabase first
            response = self.supabase.table('embeddings')\
                .select('*')\
                .eq('user_id', str(user_id))\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error getting embeddings from Supabase: {response.error}")
                return []
            
            return response.data
            
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            return []
    
    async def delete_embedding(self, embedding_id: str) -> bool:
        """Delete an embedding from both Supabase and local storage."""
        success = True
        
        # Delete from Supabase
        try:
            response = self.supabase.table('embeddings')\
                .delete()\
                .eq('id', embedding_id)\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error deleting from Supabase: {response.error}")
                success = False
                
        except Exception as e:
            logger.error(f"Error deleting from Supabase: {e}")
            success = False
        
        # Delete from local storage
        try:
            file_path = self._get_file_path(embedding_id)
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.error(f"Error deleting local backup: {e}")
            success = False
        
        return success 