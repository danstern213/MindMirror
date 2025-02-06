from typing import List, Optional
from openai import OpenAI
from ..core.config import get_settings

settings = get_settings()

class OpenAIClient:
    _instance: Optional[OpenAI] = None
    _api_key: Optional[str] = None

    @classmethod
    def get_client(cls, api_key: Optional[str] = None) -> OpenAI:
        """Get or create OpenAI client instance."""
        if api_key and (cls._instance is None or api_key != cls._api_key):
            cls._instance = OpenAI(api_key=api_key)
            cls._api_key = api_key
        elif cls._instance is None:
            cls._instance = OpenAI(api_key=settings.OPENAI_API_KEY)
            cls._api_key = settings.OPENAI_API_KEY
        return cls._instance

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
        client = OpenAIClient.get_client(api_key)
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text[:8000]  # OpenAI has a token limit
        )
        return response.data[0].embedding
    except Exception as e:
        if hasattr(e, 'status_code'):
            if e.status_code == 403:
                raise ValueError('Invalid OpenAI API key. Please check your settings.')
            elif e.status_code == 429:
                raise ValueError('OpenAI rate limit exceeded. Please try again later.')
        print('Error generating embedding:', e)
        raise 