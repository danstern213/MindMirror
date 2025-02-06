from typing import List, Optional
from supabase import Client, create_client
from .embedding_helper import generate_embedding
from ..core.config import get_settings
from ..models.file import EmbeddingCreate, EmbeddingDB
import logging

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
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap  # Create overlap with previous chunk
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
            # Split text into chunks and generate embeddings
            chunks = self.chunk_text(text)
            logger.info(f"Processing {len(chunks)} chunks for file {file_id}")
            
            embeddings = []
            # Save embeddings for each chunk
            for i, chunk in enumerate(chunks):
                try:
                    embedding = generate_embedding(chunk, api_key)
                    embedding_data = EmbeddingCreate(
                        file_id=file_id,
                        embedding=embedding,
                        text=chunk,
                        chunk_index=i,
                        user_id=user_id
                    )
                    
                    response = self.supabase.table('embeddings').insert(
                        embedding_data.model_dump(exclude={'id', 'created_at'})
                    ).execute()

                    if hasattr(response, 'error') and response.error:
                        logger.error(f"Error saving chunk {i}: {response.error}")
                    else:
                        logger.info(f"Successfully saved chunk {i} for file {file_id}")
                        embeddings.append(EmbeddingDB(**response.data[0]))
                        
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {i}: {chunk_error}")
                    raise

            return embeddings

        except Exception as e:
            logger.error(f"An error occurred while generating or saving embeddings: {str(e)}")
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