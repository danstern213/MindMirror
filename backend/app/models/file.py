from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class FileBase(BaseModel):
    filename: str
    title: str = Field(description="Display title for the file")
    storage_path: str = Field(description="Path in Supabase storage")
    user_id: UUID = Field(description="ID of the user who owns this file")
    status: str = Field(description="Status of the file: pending_embedding, indexed, failed")

class FileCreate(FileBase):
    pass

class FileDB(FileBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

class EmbeddingCreate(BaseModel):
    file_id: UUID
    embedding: List[float]
    text: str
    chunk_index: int
    user_id: UUID

class EmbeddingDB(BaseModel):
    id: UUID
    file_id: UUID
    embedding: List[float]
    text: str
    chunk_index: int
    user_id: UUID
    created_at: datetime

class FileUploadResponse(BaseModel):
    file_id: UUID
    filename: str
    upload_time: datetime
    status: str
    embedding_status: Optional[str] = None 