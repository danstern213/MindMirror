from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
from uuid import UUID
from ..core.config import get_settings

settings = get_settings()

class LinkedContext(BaseModel):
    note_path: str
    relevance: float
    context: str

class SearchResult(BaseModel):
    id: UUID
    score: float = Field(description="Relevance score from 0 to 1")
    content: str = Field(description="Matched content snippet")
    title: str = Field(description="Title of the document")
    explicit: Optional[bool] = Field(default=None, description="Whether this was an explicit reference")
    full_content: Optional[str] = None
    keyword_score: Optional[float] = None
    matched_keywords: Optional[List[str]] = None
    linked_contexts: Optional[List[LinkedContext]] = None
    document_date: Optional[date] = Field(default=None, description="Date associated with the document")

class SearchQuery(BaseModel):
    query: str
    top_k: Optional[int] = Field(default=settings.DEFAULT_SEARCH_LIMIT, description="Number of results to return")
    user_id: UUID = Field(description="ID of the user performing the search")
    include_full_content: Optional[bool] = Field(default=False, description="Whether to include full document content")
    date_start: Optional[date] = Field(default=None, description="Start date for temporal filtering")
    date_end: Optional[date] = Field(default=None, description="End date for temporal filtering") 