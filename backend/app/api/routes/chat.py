from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List, AsyncGenerator
from uuid import UUID

from ...models.chat import ChatThread, ChatRequest, ChatResponse, StreamingChatResponse
from ...services.chat_service import ChatService
from ...core.deps import get_user_id_from_supabase, get_chat_service
from ...core.config import get_settings

router = APIRouter()
settings = get_settings()

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

@router.post("/message")
async def send_message(
    request: ChatRequest,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: ChatService = Depends(get_chat_service)
) -> StreamingResponse:
    """Send a message and get a streaming response."""
    try:
        if request.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to send messages for other users"
            )
            
        # Validate message content
        if not request.message or not request.message.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content cannot be empty"
            )
            
        # Check message length
        if len(request.message) > 4000:  # Reasonable limit for message length
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message too long. Please keep messages under 4000 characters."
            )
            
        async def stream_response() -> AsyncGenerator[str, None]:
            async for chunk in service.process_message(
                content=request.message,
                thread_id=request.thread_id,
                user_id=current_user_id
            ):
                yield f"data: {chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Check for token limit errors
        if 'rate_limit_exceeded' in error_message.lower() or 'token' in error_message.lower() and 'limit' in error_message.lower():
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
            error_message = "Token limit exceeded. The system is managing your request to fit within available token limits. Please try breaking your query into smaller parts or wait a moment before trying again."
        
        # Check for other OpenAI API errors
        elif 'openai' in error_message.lower():
            if '401' in error_message or 'unauthorized' in error_message.lower():
                status_code = status.HTTP_401_UNAUTHORIZED
                error_message = "OpenAI API authentication failed. Please check your API key."
            elif '429' in error_message:
                status_code = status.HTTP_429_TOO_MANY_REQUESTS
                error_message = "OpenAI rate limit exceeded. Please try again later."
        
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to process message: {error_message}"
        ) 