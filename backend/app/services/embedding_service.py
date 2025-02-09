from typing import List, Optional
from supabase import Client, create_client
from .embedding_helper import generate_embedding
from ..core.config import get_settings
from ..models.file import EmbeddingCreate, EmbeddingDB
import logging
from datetime import datetime
from uuid import UUID, uuid4
import json

settings = get_settings()
logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self, supabase_client: Optional[Client] = None):
        """Initialize the embedding service."""
        self.supabase = supabase_client or create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )

    def chunk_text(self, text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> List[str]:
        """Split text into overlapping chunks to maintain context."""
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP
        
        if not text.strip():
            logger.warning("Empty text received for chunking")
            return []
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            # Find a good break point
            if end < len(text):
                # Try to break at paragraph or sentence
                for separator in ['\n\n', '\n', '. ']:
                    pos = text[start:end].rfind(separator)
                    if pos != -1:
                        end = start + pos + len(separator)
                        break
            chunk = text[start:end].strip()
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
            start = end - overlap  # Create overlap with previous chunk
        
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

    async def generate_and_save_embedding(
        self, 
        text: str, 
        file_id: str, 
        user_id: str,
        api_key: Optional[str] = None
    ) -> List[EmbeddingDB]:
        """Generate embeddings for text chunks and save to Supabase."""
        try:
            # Validate input
            if not text.strip():
                raise ValueError("Empty text received for embedding generation")
            
            # Convert string IDs to UUIDs
            file_uuid = UUID(file_id)
            user_uuid = UUID(user_id)
            
            # Split text into chunks
            chunks = self.chunk_text(text)
            if not chunks:
                raise ValueError("No valid chunks generated from text")
                
            logger.info(f"Processing {len(chunks)} chunks for file {file_id}")
            
            embeddings = []
            # Generate and save embeddings for all chunks at once
            embedding_data_list = []
            
            for i, chunk in enumerate(chunks):
                try:
                    # Generate embedding
                    embedding = generate_embedding(chunk, api_key)
                    if not embedding or not isinstance(embedding, list):
                        logger.error(f"Invalid embedding generated for chunk {i}")
                        continue
                    
                    # Prepare embedding data
                    embedding_data = {
                        'file_id': str(file_uuid),
                        'user_id': str(user_uuid),
                        'embedding': json.dumps(embedding),
                        'text': chunk,
                        'chunk_index': i,
                        'created_at': datetime.utcnow().isoformat()
                    }
                    embedding_data_list.append(embedding_data)
                    
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {i}: {str(chunk_error)}")
                    continue
            
            if not embedding_data_list:
                raise ValueError("No valid embeddings were generated")
            
            # Batch insert all embeddings
            response = self.supabase.table('embeddings').insert(embedding_data_list).execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error saving embeddings: {response.error}")
                raise Exception(f"Failed to save embeddings: {response.error}")
            
            # Create EmbeddingDB instances
            for item in response.data:
                embedding_db = EmbeddingDB(
                    id=item['id'],
                    file_id=file_uuid,
                    user_id=user_uuid,
                    embedding=json.loads(item['embedding']),
                    text=item['text'],
                    chunk_index=item['chunk_index'],
                    created_at=datetime.fromisoformat(item['created_at'])
                )
                embeddings.append(embedding_db)
            
            logger.info(f"Successfully saved {len(embeddings)} embeddings for file {file_id}")
            return embeddings

        except Exception as e:
            logger.error(f"Error in generate_and_save_embedding: {str(e)}", exc_info=True)
            raise

    async def get_embeddings_by_file_id(self, file_id: str) -> List[EmbeddingDB]:
        """Retrieve all embeddings for a specific file."""
        try:
            response = self.supabase.table('embeddings')\
                .select('*')\
                .eq('file_id', file_id)\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Error fetching embeddings: {response.error}")
                raise Exception(f"Error fetching embeddings: {response.error}")
            
            return [
                EmbeddingDB(
                    id=item['id'],
                    file_id=UUID(item['file_id']),
                    user_id=UUID(item['user_id']),
                    embedding=json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding'],
                    text=item['text'],
                    chunk_index=item['chunk_index'],
                    created_at=datetime.fromisoformat(item['created_at'])
                ) for item in response.data
            ]
        except Exception as e:
            logger.error(f"Error fetching embeddings for file {file_id}: {e}")
            raise 