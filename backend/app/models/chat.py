from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID

class Message(BaseModel):
    role: str = Field(description="Role of the message sender (user/assistant)")
    content: str = Field(description="Content of the message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources: Optional[List[Dict[str, Any]]] = None

class ChatThread(BaseModel):
    id: UUID
    title: str
    messages: List[Message] = Field(default_factory=list)
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: UUID

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[UUID] = None
    user_id: UUID

class ChatResponse(BaseModel):
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    thread_id: UUID
    done: bool = False

class StreamingChatResponse(ChatResponse):
    """Response model for streaming chat responses. Inherits from ChatResponse."""
    pass 