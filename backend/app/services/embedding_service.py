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
        
        # Log text statistics
        logger.info(f"Chunking text of length {len(text)} with chunk_size={chunk_size}, overlap={overlap}")
        logger.debug(f"Text preview: {text[:100]}...")
        
        # Check for potential issues
        non_ascii = sum(1 for c in text if ord(c) > 127)
        if non_ascii > 0:
            logger.warning(f"Text contains {non_ascii} non-ASCII characters")
        
        chunks = []
        start = 0
        last_start = -1  # Track last starting position to detect infinite loops
        max_iterations = (len(text) // (chunk_size - overlap)) + 2  # Maximum possible chunks plus safety margin
        iteration = 0
        
        while start < len(text) and iteration < max_iterations:
            iteration += 1
            logger.debug(f"Chunk iteration {iteration}, start position: {start}")
            
            # Detect infinite loop
            if start == last_start:
                logger.error(f"Infinite loop detected at position {start}")
                break
            last_start = start
            
            try:
                # Ensure end doesn't exceed text length
                end = min(start + chunk_size, len(text))
                
                # If we're not at the end of the text, try to find a good break point
                if end < len(text):
                    # Try to break at paragraph or sentence
                    break_found = False
                    for separator in ['\n\n', '\n', '. ', ' ']:
                        pos = text[start:end].rfind(separator)
                        if pos != -1:
                            end = start + pos + len(separator)
                            break_found = True
                            break
                    
                    if not break_found:
                        logger.warning(f"No natural break found in chunk at position {start}, using hard break")
                
                chunk = text[start:end].strip()
                
                # Validate chunk
                if chunk:
                    if len(chunk) < 10:  # Very small chunks might indicate issues
                        logger.warning(f"Very small chunk ({len(chunk)} chars) at position {start}: {chunk}")
                    chunks.append(chunk)
                    logger.debug(f"Created chunk {len(chunks)}: {chunk[:50]}...")
                
                # Ensure we're making forward progress
                new_start = end - overlap
                if new_start <= start:
                    logger.warning(f"No forward progress at position {start}, forcing advancement")
                    new_start = start + 1
                start = new_start
                
            except Exception as e:
                logger.error(f"Error processing chunk at position {start}: {str(e)}")
                # Force advancement to prevent getting stuck
                start += chunk_size // 2
        
        # Check if we hit the iteration limit
        if iteration >= max_iterations:
            logger.warning(f"Hit maximum iterations ({max_iterations}) during chunking")
        
        # Final validation
        if len(chunks) == 0:
            logger.error("No valid chunks were generated")
        else:
            logger.info(f"Split text into {len(chunks)} chunks")
            logger.info(f"Average chunk size: {sum(len(c) for c in chunks)/len(chunks):.2f} characters")
        
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
            
            # Log file details
            logger.info(f"Starting embedding generation for file {file_id}")
            logger.info(f"Text length: {len(text)}, First 100 chars: {text[:100]}")
            
            # Convert string IDs to UUIDs
            file_uuid = UUID(file_id)
            user_uuid = UUID(user_id)
            
            # Split text into chunks
            chunks = self.chunk_text(text)
            if not chunks:
                raise ValueError("No valid chunks generated from text")
                
            logger.info(f"Processing {len(chunks)} chunks for file {file_id}")
            
            embeddings = []
            embedding_data_list = []
            chunk_errors = []
            
            # Process chunks in smaller batches
            BATCH_SIZE = 5
            for batch_start in range(0, len(chunks), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(chunks))
                batch = chunks[batch_start:batch_end]
                
                logger.info(f"Processing batch {batch_start//BATCH_SIZE + 1} of {(len(chunks) + BATCH_SIZE - 1)//BATCH_SIZE}")
                
                for i, chunk in enumerate(batch):
                    chunk_index = batch_start + i
                    try:
                        logger.info(f"Processing chunk {chunk_index + 1}/{len(chunks)}")
                        logger.debug(f"Chunk preview: {chunk[:100]}...")
                        
                        # Generate embedding with timeout and retry
                        embedding = generate_embedding(chunk, api_key)
                        if not embedding or not isinstance(embedding, list):
                            error_msg = f"Invalid embedding generated for chunk {chunk_index}"
                            logger.error(error_msg)
                            chunk_errors.append(error_msg)
                            continue
                        
                        logger.info(f"Successfully generated embedding for chunk {chunk_index + 1}")
                        
                        # Prepare embedding data
                        embedding_data = {
                            'file_id': str(file_uuid),
                            'user_id': str(user_uuid),
                            'embedding': json.dumps(embedding),
                            'text': chunk,
                            'chunk_index': chunk_index,
                            'created_at': datetime.utcnow().replace(microsecond=0).isoformat()
                        }
                        embedding_data_list.append(embedding_data)
                        
                    except Exception as chunk_error:
                        error_msg = str(chunk_error)
                        logger.error(f"Error processing chunk {chunk_index}: {error_msg}")
                        chunk_errors.append(f"Chunk {chunk_index}: {error_msg}")
                        continue
                
                # Save batch to database if we have any successful embeddings
                if embedding_data_list:
                    try:
                        logger.info(f"Saving batch of {len(embedding_data_list)} embeddings to database")
                        response = self.supabase.table('embeddings').insert(embedding_data_list).execute()
                        
                        if hasattr(response, 'error') and response.error:
                            logger.error(f"Error saving embeddings batch: {response.error}")
                            chunk_errors.append(f"Failed to save batch starting at chunk {batch_start}")
                        else:
                            # Create EmbeddingDB instances for successful saves
                            for item in response.data:
                                embedding_db = EmbeddingDB(
                                    id=item['id'],
                                    file_id=file_uuid,
                                    user_id=user_uuid,
                                    embedding=json.loads(item['embedding']),
                                    text=item['text'],
                                    chunk_index=item['chunk_index'],
                                    created_at=datetime.fromisoformat(item['created_at'].replace('T', ' '))
                                )
                                embeddings.append(embedding_db)
                                
                            logger.info(f"Successfully saved batch of {len(response.data)} embeddings")
                    except Exception as save_error:
                        logger.error(f"Error saving batch: {str(save_error)}")
                        chunk_errors.append(f"Failed to save batch starting at chunk {batch_start}")
                
                # Clear batch list for next iteration
                embedding_data_list = []
            
            # Log summary
            total_chunks = len(chunks)
            successful_chunks = len(embeddings)
            failed_chunks = len(chunk_errors)
            
            logger.info(f"Embedding generation complete: {successful_chunks}/{total_chunks} chunks successful")
            if chunk_errors:
                logger.warning(f"Failed chunks ({failed_chunks}): {'; '.join(chunk_errors)}")
            
            if successful_chunks == 0:
                raise ValueError("No embeddings were successfully generated and saved")
            
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
                    created_at=datetime.fromisoformat(item['created_at'].replace('T', ' '))
                ) for item in response.data
            ]
        except Exception as e:
            logger.error(f"Error fetching embeddings for file {file_id}: {e}")
            raise 