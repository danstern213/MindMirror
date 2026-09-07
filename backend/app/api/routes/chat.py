from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List, AsyncGenerator
from uuid import UUID
import logging

from ...models.chat import ChatThread, ChatRequest, ChatResponse, StreamingChatResponse, Message
from ...services.chat_service import ChatService
from ...core.deps import get_user_id_from_supabase, get_user_id_from_auth, get_chat_service
from ...core.config import get_settings

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


def _error_text(e: Exception) -> str:
    """
    Flatten an exception and everything it wraps into one searchable string.

    Retry wrappers hide the real cause: tenacity's RetryError stringifies to
    "RetryError[<Future ... raised ValueError>]", which mentions neither the
    provider nor the status code, so classifying on str(e) alone loses the
    only information worth showing the user.
    """
    parts: List[str] = []
    seen = set()
    queue = [e]
    while queue:
        exc = queue.pop()
        if exc is None or id(exc) in seen:
            continue
        seen.add(id(exc))
        parts.append(str(exc))
        # tenacity.RetryError keeps the failed attempt around
        last_attempt = getattr(exc, 'last_attempt', None)
        if last_attempt is not None and hasattr(last_attempt, 'exception'):
            try:
                queue.append(last_attempt.exception())
            except Exception:  # future was cancelled / never completed
                pass
        queue.append(getattr(exc, '__cause__', None))
        queue.append(getattr(exc, '__context__', None))
    return " | ".join(parts)


def _classify_error(e: Exception) -> tuple[int, str]:
    """Map an exception to an HTTP status code and a user-facing message."""
    if isinstance(e, HTTPException):
        return e.status_code, str(e.detail)

    error_message = _error_text(e)
    lowered = error_message.lower()

    # Billing exhaustion. This is NOT a transient rate limit and retrying will
    # never help, so say plainly what has to happen.
    if 'insufficient_quota' in lowered or 'credit_balance_exhausted' in lowered \
            or 'no credits remaining' in lowered or 'exceeded your current quota' in lowered:
        return (
            status.HTTP_402_PAYMENT_REQUIRED,
            "The OpenAI account has no credits remaining, so notes cannot be searched. "
            "Add credits at platform.openai.com/settings/organization/billing."
        )

    # Token / rate limit errors
    if 'rate_limit_exceeded' in lowered or ('token' in lowered and 'limit' in lowered):
        return (
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Token limit exceeded. Please try breaking your query into smaller parts "
            "or wait a moment before trying again."
        )

    # Model misconfiguration — surface the model name so it is obvious what to fix
    if 'model_not_found' in lowered or ('model' in lowered and 'does not exist' in lowered):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"The configured chat model '{settings.OPENAI_MODEL}' was rejected by OpenAI. "
            f"Check the OPENAI_MODEL environment variable."
        )

    # These are matched on the flattened text, so they also catch errors that
    # only name the provider via their exception class rather than their message.
    if 'invalid_api_key' in lowered or 'unauthorized' in lowered or 'error code: 401' in lowered:
        return status.HTTP_401_UNAUTHORIZED, "OpenAI API authentication failed. Please check your API key."

    if 'error code: 429' in lowered or 'too many requests' in lowered:
        return status.HTTP_429_TOO_MANY_REQUESTS, "OpenAI rate limit exceeded. Please try again later."

    return status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to process message: {error_message}"


def _user_facing_error(e: Exception) -> str:
    return _classify_error(e)[1]

@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    title: str = "New Chat",
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> ChatThread:
    """Create a new chat thread."""
    try:
        return await service.create_thread(current_user_id, title)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create thread: {str(e)}"
        )

@router.get("/threads")
async def list_threads(
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> List[ChatThread]:
    """List all chat threads for the current user."""
    try:
        return await service.get_user_threads(current_user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list threads: {str(e)}"
        )

@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> ChatThread:
    """Get a specific chat thread."""
    try:
        thread = await service.get_thread(thread_id, current_user_id)
        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found"
            )
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get thread: {str(e)}"
        )

@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> dict:
    """Delete a chat thread."""
    try:
        success = await service.delete_thread(thread_id, current_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete thread"
            )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete thread: {str(e)}"
        )

@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> List[Message]:
    """Get all messages for a specific chat thread (lazy loading)."""
    try:
        messages = await service.get_thread_messages(thread_id, current_user_id)
        return messages
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load thread messages: {str(e)}"
        )

@router.post("/message")
async def send_message(
    request: ChatRequest,
    current_user_id: UUID = Depends(get_user_id_from_auth),
    service: ChatService = Depends(get_chat_service)
) -> StreamingResponse:
    """Send a message and get a streaming response."""
    try:
        logger.info(f"[MESSAGE] send_message called - user_id: {current_user_id}, thread_id: {request.thread_id}, message_preview: {request.message[:50] if request.message else 'None'}...")
        
        if request.user_id != current_user_id:
            logger.warning(f"[MESSAGE] Authorization failed - request.user_id: {request.user_id}, current_user_id: {current_user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to send messages for other users"
            )
            
        # Validate message content
        if not request.message or not request.message.strip():
            logger.warning("[MESSAGE] Empty message received")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content cannot be empty"
            )
            
        # Check message length
        if len(request.message) > 4000:  # Reasonable limit for message length
            logger.warning(f"[MESSAGE] Message too long: {len(request.message)} characters")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message too long. Please keep messages under 4000 characters."
            )
        
        logger.info("[MESSAGE] Creating stream_response generator")
        async def stream_response() -> AsyncGenerator[str, None]:
            chunk_count = 0
            try:
                logger.info("[MESSAGE] Starting to iterate over process_message generator")
                async for chunk in service.process_message(
                    content=request.message,
                    thread_id=request.thread_id,
                    user_id=current_user_id
                ):
                    chunk_count += 1
                    logger.debug(f"[MESSAGE] Yielding chunk #{chunk_count}, content_length: {len(chunk.content) if chunk.content else 0}")
                    yield f"data: {chunk.model_dump_json()}\n\n"
                logger.info(f"[MESSAGE] Finished iterating - total chunks: {chunk_count}, sending [DONE]")
                yield "data: [DONE]\n\n"
            except Exception as e:
                # The 200 OK and headers are already on the wire by the time the body
                # generator runs, so raising here just truncates the stream and the
                # client sees a silent, empty response. Emit the failure as an SSE
                # event instead so the frontend can surface it.
                logger.error(f"[MESSAGE] Error in stream_response generator: {e}", exc_info=True)
                error_chunk = StreamingChatResponse(
                    content="",
                    sources=[],
                    thread_id=request.thread_id or UUID(int=0),
                    done=True,
                    error=_user_facing_error(e)
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
        
        logger.info("[MESSAGE] Returning StreamingResponse")
        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        status_code, error_message = _classify_error(e)
        raise HTTPException(status_code=status_code, detail=error_message) 