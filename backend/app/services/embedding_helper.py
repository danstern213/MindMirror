from typing import List, Optional
from openai import OpenAI
from ..core.config import get_settings
import logging
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

settings = get_settings()
logger = logging.getLogger(__name__)

# Constants for timeouts and retries
EMBEDDING_TIMEOUT = 30  # 30 seconds timeout for embedding generation
MAX_RETRIES = 3
INITIAL_WAIT = 1  # Initial wait time between retries in seconds

class OpenAIClient:
    _instance: Optional[OpenAI] = None
    _api_key: Optional[str] = None

    @classmethod
    def get_client(cls, api_key: Optional[str] = None) -> OpenAI:
        """Get or create OpenAI client instance."""
        try:
            if api_key and (cls._instance is None or api_key != cls._api_key):
                logger.info("Creating new OpenAI client with provided API key")
                cls._instance = OpenAI(api_key=api_key, timeout=EMBEDDING_TIMEOUT)
                cls._api_key = api_key
            elif cls._instance is None:
                logger.info("Creating new OpenAI client with settings API key")
                cls._instance = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=EMBEDDING_TIMEOUT)
                cls._api_key = settings.OPENAI_API_KEY
            return cls._instance
        except Exception as e:
            logger.error(f"Error creating OpenAI client: {str(e)}")
            raise

@retry(stop=stop_after_attempt(MAX_RETRIES), 
       wait=wait_exponential(multiplier=INITIAL_WAIT, min=1, max=10))
def generate_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Generate an embedding for the given text using OpenAI's API.
    
    Args:
        text: The input text to embed
        api_key: Optional API key (will use settings if not provided)
    
    Returns:
        List[float]: The embedding vector
    """
    try:
        # Input validation and sanitization
        if not text or not text.strip():
            logger.warning("Empty or whitespace-only text received")
            raise ValueError("Cannot generate embedding for empty text")

        # Log the first and last few characters of the text for debugging
        text_preview = f"{text[:50]}...{text[-50:]}" if len(text) > 100 else text
        logger.info(f"Generating embedding for text preview: {text_preview}")
        logger.debug(f"Text length: {len(text)}, Character types: {set(text[:100])}")
        
        # Sanitize text - handle non-ASCII characters
        sanitized_text = text
        
        # Check for and handle non-ASCII characters
        if any(ord(c) > 127 for c in text[:100]):
            logger.info("Text contains non-ASCII characters, applying sanitization")
            # Replace common smart quotes and special characters with ASCII equivalents
            char_replacements = {
                '"': '"',  # Smart quotes
                '"': '"',
                ''': "'",  # Smart apostrophes
                ''': "'",
                '–': '-',  # En dash
                '—': '-',  # Em dash
                '…': '...',  # Ellipsis
                '\u200b': '',  # Zero-width space
                '\xa0': ' ',  # Non-breaking space
            }
            
            # Apply character replacements
            for old, new in char_replacements.items():
                sanitized_text = sanitized_text.replace(old, new)
            
            # For any remaining non-ASCII characters, try to normalize them
            import unicodedata
            sanitized_text = unicodedata.normalize('NFKD', sanitized_text).encode('ascii', 'ignore').decode('ascii')
            
            logger.info("Text sanitization complete")
        
        client = OpenAIClient.get_client(api_key)
        
        # Further sanitize and truncate text
        # Replace problematic characters and normalize whitespace
        sanitized_text = ' '.join(sanitized_text.replace('\x00', ' ').split())
        truncated_text = sanitized_text[:8000]  # OpenAI has a token limit
        
        if len(text) > 8000:
            logger.warning(f"Text truncated from {len(text)} to 8000 characters")
            
        if not truncated_text.strip():
            logger.error("Text became empty after sanitization")
            raise ValueError("Text became empty after sanitization")
        
        logger.info(f"Using embedding model: {settings.EMBEDDING_MODEL}")
        logger.debug("Making API call to OpenAI")
        
        try:
            response = client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=truncated_text
            )
            
            if not response or not response.data:
                logger.error("Empty response from OpenAI API")
                raise ValueError("Empty response from OpenAI API")
                
            embedding = response.data[0].embedding
            embedding_length = len(embedding)
            logger.info(f"Successfully generated embedding of dimension {embedding_length}")
            
            # Validate embedding
            if not embedding_length > 0:
                raise ValueError(f"Invalid embedding dimension: {embedding_length}")
                
            return embedding
            
        except asyncio.TimeoutError:
            logger.error("Embedding generation timed out")
            raise ValueError("Embedding generation timed out. Please try again.")
            
    except Exception as e:
        if hasattr(e, 'status_code'):
            if e.status_code == 403:
                logger.error("OpenAI API authentication failed")
                raise ValueError('Invalid OpenAI API key. Please check your settings.')
            elif e.status_code == 429:
                logger.error("OpenAI API rate limit exceeded")
                raise ValueError('OpenAI rate limit exceeded. Please try again later.')
            else:
                logger.error(f"OpenAI API error (status {e.status_code}): {str(e)}")
        else:
            logger.error(f"Error generating embedding: {str(e)}", exc_info=True)
        raise 