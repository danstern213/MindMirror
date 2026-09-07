from typing import List, Optional
from openai import OpenAI, AsyncOpenAI
from ..core.config import get_settings
import logging
import asyncio
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

settings = get_settings()
logger = logging.getLogger(__name__)

# Constants for timeouts and retries
EMBEDDING_TIMEOUT = 30  # 30 seconds timeout for embedding generation
MAX_RETRIES = 3
INITIAL_WAIT = 1  # Initial wait time between retries in seconds


class AsyncOpenAIClient:
    """
    Async twin of OpenAIClient, and the one every request handler should use.

    The synchronous client stalls the whole event loop for the duration of each
    HTTP call, so one user's search blocks every other user's request.
    """
    _instance: Optional[AsyncOpenAI] = None
    _api_key: Optional[str] = None

    @classmethod
    def get_client(cls, api_key: Optional[str] = None) -> AsyncOpenAI:
        if api_key and (cls._instance is None or api_key != cls._api_key):
            logger.info("Creating new async OpenAI client with provided API key")
            cls._instance = AsyncOpenAI(api_key=api_key, timeout=EMBEDDING_TIMEOUT)
            cls._api_key = api_key
        elif cls._instance is None:
            logger.info("Creating new async OpenAI client with settings API key")
            cls._instance = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=EMBEDDING_TIMEOUT)
            cls._api_key = settings.OPENAI_API_KEY
        return cls._instance


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

# Errors that will never succeed on a retry. Without this the caller pays
# MAX_RETRIES x the SDK's own internal retries (9 HTTP calls) waiting out a
# billing or credentials problem that a retry cannot fix.
_PERMANENT_ERROR_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "no credits remaining",
    "exceeded your current quota",
    "invalid_api_key",
    "invalid api key",
)


def _is_retryable(exc: BaseException) -> bool:
    text = str(exc).lower()
    if any(marker in text for marker in _PERMANENT_ERROR_MARKERS):
        logger.error(f"Not retrying permanent OpenAI error: {exc}")
        return False
    return True



_RETRY_POLICY = dict(
    stop=stop_after_attempt(MAX_RETRIES),
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=INITIAL_WAIT, min=1, max=10),
    reraise=True,
)

# Characters OpenAI's tokenizer handles poorly, mapped to ASCII equivalents.
_CHAR_REPLACEMENTS = {
    '\u201c': '"', '\u201d': '"',      # smart quotes
    '\u2018': "'", '\u2019': "'",      # smart apostrophes
    '\u2013': '-', '\u2014': '-',      # en/em dash
    '\u2026': '...',                   # ellipsis
    '\u200b': '',                      # zero-width space
    '\xa0': ' ',                       # non-breaking space
}

# ada-002 and the text-embedding-3 family all cap input at 8191 tokens.
_MAX_EMBEDDING_TOKENS = 8191


def _prepare_text(text: str) -> str:
    """
    Validate, sanitize and truncate text before embedding.

    Shared by the sync and async entry points so the two cannot drift apart.
    """
    if not text or not text.strip():
        logger.warning("Empty or whitespace-only text received")
        raise ValueError("Cannot generate embedding for empty text")

    text_preview = f"{text[:50]}...{text[-50:]}" if len(text) > 100 else text
    logger.info(f"Generating embedding for text preview: {text_preview}")

    sanitized_text = text
    if any(ord(c) > 127 for c in text[:100]):
        logger.info("Text contains non-ASCII characters, applying sanitization")
        for old, new in _CHAR_REPLACEMENTS.items():
            sanitized_text = sanitized_text.replace(old, new)
        import unicodedata
        sanitized_text = unicodedata.normalize('NFKD', sanitized_text).encode('ascii', 'ignore').decode('ascii')

    # Normalize whitespace and strip NULs, which PostgREST rejects downstream.
    sanitized_text = ' '.join(sanitized_text.replace('\x00', ' ').split())

    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(sanitized_text)
        if len(tokens) > _MAX_EMBEDDING_TOKENS:
            logger.warning(f"Text has {len(tokens)} tokens, exceeding the limit. Truncating.")
            sanitized_text = encoding.decode(tokens[:_MAX_EMBEDDING_TOKENS])
        else:
            logger.info(f"Text has {len(tokens)} tokens, under the {_MAX_EMBEDDING_TOKENS} limit.")
    except ImportError:
        logger.warning("tiktoken not available, using character-based truncation")
        sanitized_text = sanitized_text[:8000]

    if not sanitized_text.strip():
        logger.error("Text became empty after sanitization")
        raise ValueError("Text became empty after sanitization")

    return sanitized_text


def _extract_embedding(response) -> List[float]:
    """Pull the vector out of an embeddings response, validating as we go."""
    if not response or not response.data:
        logger.error("Empty response from OpenAI API")
        raise ValueError("Empty response from OpenAI API")

    embedding = response.data[0].embedding
    if not embedding:
        raise ValueError(f"Invalid embedding dimension: {len(embedding) if embedding else 0}")

    logger.info(f"Successfully generated embedding of dimension {len(embedding)}")
    return embedding


def _translate_openai_error(e: Exception) -> None:
    """
    Re-raise an OpenAI exception as a ValueError with an actionable message.

    Always raises; the return type is None only because it never returns.
    """
    status_code = getattr(e, 'status_code', None)
    if status_code == 403:
        logger.error("OpenAI API authentication failed")
        raise ValueError('Invalid OpenAI API key. Please check your settings.') from e
    if status_code == 429:
        # A 429 is either a transient rate limit or a hard billing stop, and they
        # need opposite handling. Keep the distinguishing marker in the message so
        # _is_retryable and the API layer can tell them apart.
        if 'insufficient_quota' in str(e) or 'credit_balance_exhausted' in str(e):
            logger.error("OpenAI account is out of credits")
            raise ValueError(
                'OpenAI credit_balance_exhausted (insufficient_quota): '
                'the account has no credits remaining.'
            ) from e
        logger.error("OpenAI API rate limit exceeded")
        raise ValueError('OpenAI rate limit exceeded. Please try again later.') from e

    if status_code is not None:
        logger.error(f"OpenAI API error (status {status_code}): {e}")
    else:
        logger.error(f"Error generating embedding: {e}", exc_info=True)
    raise e


@retry(**_RETRY_POLICY)
async def generate_embedding_async(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Generate an embedding without blocking the event loop.

    Prefer this over generate_embedding() anywhere inside a request handler.
    """
    try:
        prepared = _prepare_text(text)
        client = AsyncOpenAIClient.get_client(api_key)
        logger.info(f"Using embedding model: {settings.EMBEDDING_MODEL}")
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=prepared
        )
        return _extract_embedding(response)
    except asyncio.TimeoutError as e:
        logger.error("Embedding generation timed out")
        raise ValueError("Embedding generation timed out. Please try again.") from e
    except Exception as e:
        _translate_openai_error(e)


@retry(**_RETRY_POLICY)
def generate_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Blocking embedding generation, for synchronous callers such as CLI scripts.

    Inside async code use generate_embedding_async() instead.
    """
    try:
        prepared = _prepare_text(text)
        client = OpenAIClient.get_client(api_key)
        logger.info(f"Using embedding model: {settings.EMBEDDING_MODEL}")
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=prepared
        )
        return _extract_embedding(response)
    except Exception as e:
        _translate_openai_error(e)
