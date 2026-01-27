from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID

class FileBase(BaseModel):
    filename: str
    title: str = Field(description="Display title for the file")
    storage_path: str = Field(description="Path in Supabase storage")
    user_id: UUID = Field(description="ID of the user who owns this file")
    status: str = Field(description="Status of the file: pending_embedding, indexed, failed")
    document_date: Optional[date] = Field(default=None, description="Date extracted from filename for temporal search")
    date_source: Optional[str] = Field(default=None, description="Source of document_date: filename, content, or created_at")

    class Config:
        json_encoders = {
            UUID: str,  # Convert UUID to string when serializing
            date: lambda v: v.isoformat() if v else None  # Convert date to ISO string
        }

class FileCreate(FileBase):
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Ensure UUID is converted to string
        data['user_id'] = str(data['user_id'])
        # Convert date to ISO string for database
        if data.get('document_date'):
            data['document_date'] = data['document_date'].isoformat()
        return data

class FileDB(FileBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Ensure UUIDs are converted to strings
        data['id'] = str(data['id'])
        data['user_id'] = str(data['user_id'])
        # Convert date to ISO string
        if data.get('document_date'):
            data['document_date'] = data['document_date'].isoformat() if hasattr(data['document_date'], 'isoformat') else data['document_date']
        return data

class EmbeddingCreate(BaseModel):
    file_id: UUID
    embedding: List[float]
    text: str
    chunk_index: int
    user_id: UUID

    class Config:
        json_encoders = {
            UUID: str
        }

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Ensure UUIDs are converted to strings
        data['file_id'] = str(data['file_id'])
        data['user_id'] = str(data['user_id'])
        return data

class EmbeddingDB(BaseModel):
    id: int  # Changed from UUID to int for bigInt compatibility
    file_id: UUID
    user_id: UUID
    embedding: List[float]
    text: str
    chunk_index: int
    created_at: datetime

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Convert UUIDs to strings, leave id as int
        data['file_id'] = str(data['file_id'])
        data['user_id'] = str(data['user_id'])
        # Ensure embedding is a list
        if isinstance(data['embedding'], str):
            import json
            data['embedding'] = json.loads(data['embedding'])
        return data

class FileUploadResponse(BaseModel):
    file_id: UUID
    filename: str
    upload_time: datetime
    status: str
    embedding_status: Optional[str] = None

    class Config:
        json_encoders = {
            UUID: str
        } 