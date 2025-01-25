from typing import List, Optional, TypedDict
import aiofiles
import json
import os
from pathlib import Path
from supabase import create_client, Client
import streamlit as st

class Embedding(TypedDict):
    id: str
    embedding: List[float]
    last_modified: Optional[float]

class StorageService:
    """
    Storage service for managing embeddings.
    Replaces localforage with a file-based storage system.
    """
    
    def __init__(self, storage_dir: str = "adil-clone/embeddings"):
        # Keep local storage for backup/fallback
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Supabase client
        self.supabase: Client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
    
    def _get_file_path(self, embedding_id: str) -> Path:
        """Get the file path for an embedding ID."""
        # Use a hash or encode the ID to ensure valid filename
        safe_id = embedding_id.replace('/', '_').replace('\\', '_')
        return self.storage_dir / f"{safe_id}.json"
    
    async def save_embedding(self, embedding: Embedding) -> None:
        """Save embedding to both Supabase and local storage."""
        # Save to Supabase
        try:
            self.supabase.table('embeddings').insert({
                'file_id': embedding['id'],
                'embedding': embedding['embedding'],
                'last_modified': embedding['last_modified']
            }).execute()
        except Exception as e:
            print(f"Error saving to Supabase: {e}")
            
        # Backup to local storage
        file_path = self._get_file_path(embedding['id'])
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(json.dumps(embedding))
    
    async def get_embedding(self, embedding_id: str) -> Optional[Embedding]:
        """Get embedding from Supabase or fall back to local storage."""
        try:
            # Try Supabase first
            result = self.supabase.table('embeddings') \
                .select('*') \
                .eq('file_id', embedding_id) \
                .execute()
            
            if result.data:
                return {
                    'id': result.data[0]['file_id'],
                    'embedding': result.data[0]['embedding'],
                    'last_modified': result.data[0]['last_modified']
                }
        except Exception as e:
            print(f"Error getting from Supabase: {e}")
        
        # Fall back to local storage
        file_path = self._get_file_path(embedding_id)
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return None
    
    async def get_all_embeddings(self) -> List[Embedding]:
        """Get all embeddings from Supabase or fall back to local storage."""
        embeddings = []
        try:
            # Try Supabase first
            result = self.supabase.table('embeddings').select('*').execute()
            return [
                {
                    'id': row['file_id'],
                    'embedding': row['embedding'],
                    'last_modified': row['last_modified']
                }
                for row in result.data
            ]
        except Exception as e:
            print(f"Error getting embeddings from Supabase: {e}, falling back to local")
            # Fall back to local storage
            for file_path in self.storage_dir.glob('*.json'):
                try:
                    async with aiofiles.open(file_path, 'r') as f:
                        content = await f.read()
                        embedding = json.loads(content)
                        embeddings.append(embedding)
                except Exception as e:
                    print(f"Error reading embedding {file_path}: {e}")
        
        return embeddings
    
    async def delete_embedding(self, embedding_id: str) -> None:
        """Delete an embedding from storage."""
        file_path = self._get_file_path(embedding_id)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass

# Create a global instance
_storage_service = StorageService()

# Export functions that match the original TypeScript interface
async def save_embedding(embedding: Embedding) -> None:
    await _storage_service.save_embedding(embedding)

async def get_embedding(embedding_id: str) -> Optional[Embedding]:
    return await _storage_service.get_embedding(embedding_id)

async def get_all_embeddings() -> List[Embedding]:
    return await _storage_service.get_all_embeddings()

async def delete_embedding(embedding_id: str) -> None:
    await _storage_service.delete_embedding(embedding_id) 