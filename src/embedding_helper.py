import streamlit as st
from typing import List, Optional, Union
import openai
from openai import OpenAI

# Global client instance - using Union instead of |
client: Union[OpenAI, None] = None

def initialize_openai(api_key: str = None) -> None:
    """Initialize the OpenAI client."""
    global client
    if not api_key:
        api_key = st.secrets.get('OPENAI_API_KEY')
    
    if not api_key:
        raise ValueError('OpenAI API key not found in secrets or provided')
    
    client = OpenAI(api_key=api_key)
    print('OpenAI client initialized successfully')

def generate_embedding(text: str, api_key: str = None) -> List[float]:
    """
    Generate an embedding for the given text using OpenAI's API.
    
    Args:
        text: The input text to embed
        api_key: Optional API key (will use secrets if not provided)
    
    Returns:
        List[float]: The embedding vector
    """
    global client
    if not api_key:
        api_key = st.secrets.get('OPENAI_API_KEY')
    
    if not api_key:
        raise ValueError('OpenAI API key not found in secrets or provided')

    # Reinitialize if API key changed or client not initialized
    if not client or client.api_key != api_key:
        initialize_openai(api_key)

    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text[:8000]  # OpenAI has a token limit
        )
        return response.data[0].embedding
    except openai.APIError as error:
        if error.status_code == 403:
            raise ValueError('Invalid OpenAI API key. Please check your settings.')
        elif error.status_code == 429:
            raise ValueError('OpenAI rate limit exceeded. Please try again later.')
        print('Error generating embedding:', error)
        raise 