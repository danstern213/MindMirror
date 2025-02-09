from typing import List, Optional
from openai import OpenAI
from ..core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class OpenAIClient:
    _instance: Optional[OpenAI] = None
    _api_key: Optional[str] = None

    @classmethod
    def get_client(cls, api_key: Optional[str] = None) -> OpenAI:
        """Get or create OpenAI client instance."""
        try:
            if api_key and (cls._instance is None or api_key != cls._api_key):
                logger.info("Creating new OpenAI client with provided API key")
                cls._instance = OpenAI(api_key=api_key)
                cls._api_key = api_key
            elif cls._instance is None:
                logger.info("Creating new OpenAI client with settings API key")
                cls._instance = OpenAI(api_key=settings.OPENAI_API_KEY)
                cls._api_key = settings.OPENAI_API_KEY
            return cls._instance
        except Exception as e:
            logger.error(f"Error creating OpenAI client: {str(e)}")
            raise

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
        logger.info("Generating embedding for text")
        logger.debug(f"Text length: {len(text)}")
        
        client = OpenAIClient.get_client(api_key)
        truncated_text = text[:8000]  # OpenAI has a token limit
        
        if len(text) > 8000:
            logger.warning(f"Text truncated from {len(text)} to 8000 characters")
        
        logger.info(f"Using embedding model: {settings.EMBEDDING_MODEL}")
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=truncated_text
        )
        
        embedding = response.data[0].embedding
        logger.info(f"Successfully generated embedding of dimension {len(embedding)}")
        return embedding
        
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