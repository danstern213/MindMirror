from typing import List, Optional, TypedDict, Dict
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[Dict] = None

@dataclass
class ChatThread:
    """Represents a conversation thread."""
    id: str
    title: str
    messages: List[Message]
    created: datetime
    last_updated: datetime
    context: Optional[str] = None
    summary: Optional[str] = None

class ThreadStorage(TypedDict):
    """Storage format for chat threads."""
    version: int
    threads: List[ChatThread]

@dataclass
class ChatEvent:
    """Base class for chat-related events."""
    type: str
    thread_id: str
    timestamp: datetime

@dataclass
class MessageEvent(ChatEvent):
    """Event for new messages."""
    message: Message

@dataclass
class ThreadEvent(ChatEvent):
    """Event for thread-related changes."""
    thread: ChatThread 