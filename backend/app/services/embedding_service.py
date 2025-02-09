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
            
            # Split text into chunks and generate embeddings
            chunks = self.chunk_text(text)
            if not chunks:
                raise ValueError("No valid chunks generated from text")
                
            logger.info(f"Processing {len(chunks)} chunks for file {file_id}")
            
            embeddings = []
            # Save embeddings for each chunk
            for i, chunk in enumerate(chunks):
                try:
                    # Generate embedding
                    embedding = generate_embedding(chunk, api_key)
                    if not embedding:
                        logger.error(f"Failed to generate embedding for chunk {i}")
                        continue
                        
                    # Validate embedding
                    if not isinstance(embedding, list) or not all(isinstance(x, float) for x in embedding):
                        logger.error(f"Invalid embedding format for chunk {i}")
                        continue
                    
                    # Create embedding data
                    embedding_data = {
                        # Remove the id field to let Supabase auto-increment
                        'file_id': str(file_uuid),
                        'user_id': str(user_uuid),
                        'embedding': json.dumps(embedding),  # Ensure embedding is JSON serializable
                        'text': chunk,
                        'chunk_index': i,
                        'created_at': datetime.utcnow().isoformat()
                    }
                    
                    # Save to Supabase
                    response = self.supabase.table('embeddings').insert(embedding_data).execute()

                    if hasattr(response, 'error') and response.error:
                        logger.error(f"Error saving chunk {i}: {response.error}")
                        raise Exception(f"Failed to save embedding: {response.error}")
                    
                    if not response.data or not isinstance(response.data, list) or not response.data[0]:
                        logger.error(f"Invalid response data format: {response.data}")
                        raise Exception("Invalid response data format from Supabase")
                    
                    # Create EmbeddingDB instance
                    embedding_db = EmbeddingDB(
                        id=response.data[0]['id'],  # This will be a bigInt from Supabase
                        file_id=file_uuid,
                        user_id=user_uuid,
                        embedding=embedding,
                        text=chunk,
                        chunk_index=i,
                        created_at=datetime.fromisoformat(response.data[0].get('created_at'))
                    )
                    
                    logger.info(f"Successfully saved chunk {i} for file {file_id}")
                    embeddings.append(embedding_db)
                        
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {i}: {str(chunk_error)}", exc_info=True)
                    raise Exception(f"Failed to process chunk {i}: {str(chunk_error)}")

            if not embeddings:
                raise Exception("No embeddings were successfully generated and saved")

            return embeddings

        except Exception as e:
            logger.error(f"An error occurred while generating or saving embeddings: {str(e)}", exc_info=True)
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
            
            return [EmbeddingDB(**item) for item in response.data]
        except Exception as e:
            logger.error(f"Error fetching embeddings for file {file_id}: {e}")
            raise 