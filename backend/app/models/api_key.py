"""Pydantic models for API key management."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateAPIKeyRequest(BaseModel):
    """Request model for creating an API key."""
    name: str = Field(..., min_length=1, max_length=100, description="A name to identify this API key")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Number of days until the key expires (optional)")


class CreateAPIKeyResponse(BaseModel):
    """Response model for API key creation - includes plaintext key (shown only once)."""
    id: UUID
    name: str
    key_prefix: str = Field(..., description="First 8 characters of the key for identification")
    key: str = Field(..., description="The full API key - save this, it won't be shown again")
    created_at: datetime
    expires_at: Optional[datetime] = None


class APIKeyInfo(BaseModel):
    """API key metadata without the plaintext key."""
    id: UUID
    name: str
    key_prefix: str = Field(..., description="First 8 characters of the key for identification")
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
