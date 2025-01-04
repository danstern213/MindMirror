from typing import List, Optional, TypedDict
import aiofiles
import json
import os
from pathlib import Path

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
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, embedding_id: str) -> Path:
        """Get the file path for an embedding ID."""
        # Use a hash or encode the ID to ensure valid filename
        safe_id = embedding_id.replace('/', '_').replace('\\', '_')
        return self.storage_dir / f"{safe_id}.json"
    
    async def save_embedding(self, embedding: Embedding) -> None:
        """Save an embedding to storage."""
        file_path = self._get_file_path(embedding['id'])
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(json.dumps(embedding))
    
    async def get_embedding(self, embedding_id: str) -> Optional[Embedding]:
        """Retrieve an embedding from storage."""
        file_path = self._get_file_path(embedding_id)
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return None
    
    async def get_all_embeddings(self) -> List[Embedding]:
        """Retrieve all embeddings from storage."""
        embeddings: List[Embedding] = []
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