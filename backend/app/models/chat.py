from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class Message(BaseModel):
    role: str = Field(description="Role of the message sender (user/assistant)")
    content: str = Field(description="Content of the message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: Optional[List[Dict[str, Any]]] = None

class ChatThread(BaseModel):
    id: UUID
    title: str
    messages: List[Message] = Field(default_factory=list)
    created: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
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