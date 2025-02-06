from typing import Optional, List
from fastapi import UploadFile, HTTPException
import aiofiles
import os
import re
from datetime import datetime
from uuid import UUID, uuid4
from supabase import Client, create_client
from .embedding_service import EmbeddingService
from ..models.file import FileCreate, FileDB, FileUploadResponse
from ..core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class UploadService:
    def __init__(
        self,
        supabase_client: Optional[Client] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        """Initialize the upload service."""
        self.supabase = supabase_client or create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        self.embedding_service = embedding_service or EmbeddingService(self.supabase)

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize the filename to be safe for storage."""
        return re.sub(r'[^\w\-_\. ]', '_', filename)

    def _check_file_size(self, file_size: int) -> None:
        """Check if file size is within limits."""
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE} bytes"
            )

    def _check_file_extension(self, filename: str) -> None:
        """Check if file extension is allowed."""
        ext = filename.split('.')[-1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"File extension .{ext} not allowed. Allowed extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

    async def save_file(
        self,
        file: UploadFile,
        user_id: UUID,
        api_key: Optional[str] = None
    ) -> FileUploadResponse:
        """Save file to storage and generate embeddings."""
        try:
            # Validate file
            content = await file.read()
            self._check_file_size(len(content))
            self._check_file_extension(file.filename)
            
            # Create unique filename
            file_id = uuid4()
            sanitized_filename = self._sanitize_filename(file.filename)
            storage_path = f"{user_id}/{file_id}/{sanitized_filename}"

            # Upload to Supabase storage
            storage_response = self.supabase.storage.from_('documents').upload(
                storage_path,
                content
            )

            if hasattr(storage_response, 'error') and storage_response.error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error uploading file: {storage_response.error['message']}"
                )

            # Save file metadata
            file_data = FileCreate(
                filename=file.filename,
                storage_path=storage_path,
                title=file.filename,
                user_id=user_id,
                status='pending_embedding'
            )

            file_response = self.supabase.table('files').insert(
                file_data.model_dump()
            ).execute()

            if hasattr(file_response, 'error') and file_response.error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error saving file metadata: {file_response.error['message']}"
                )

            file_record = FileDB(**file_response.data[0])

            # Generate embeddings asynchronously
            text_content = content.decode('utf-8')
            await self.embedding_service.generate_and_save_embedding(
                text_content,
                str(file_record.id),
                str(user_id),
                api_key
            )

            # Update file status
            self.supabase.table('files').update({
                'status': 'indexed'
            }).eq('id', file_record.id).execute()

            return FileUploadResponse(
                file_id=file_record.id,
                filename=file_record.filename,
                upload_time=file_record.created_at,
                status="success",
                embedding_status="completed"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"An error occurred while processing the file: {str(e)}"
            )

    async def get_user_files(self, user_id: UUID) -> List[FileDB]:
        """Fetch the list of files for a user."""
        try:
            response = self.supabase.table('files')\
                .select('*')\
                .eq('user_id', str(user_id))\
                .execute()

            if hasattr(response, 'error') and response.error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error fetching files: {response.error['message']}"
                )

            return [FileDB(**item) for item in response.data]
        except Exception as e:
            logger.error(f"Error fetching files for user {user_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching user files: {str(e)}"
            )

    async def get_file_content(self, file_id: UUID, user_id: UUID) -> str:
        """Get the content of a file."""
        try:
            # First verify the file belongs to the user
            file_response = self.supabase.table('files')\
                .select('*')\
                .eq('id', str(file_id))\
                .eq('user_id', str(user_id))\
                .single()\
                .execute()

            if not file_response.data:
                raise HTTPException(status_code=404, detail="File not found")

            file_record = FileDB(**file_response.data)

            # Download the file content
            content = self.supabase.storage.from_('documents')\
                .download(file_record.storage_path)

            return content.decode('utf-8')
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching content for file {file_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching file content: {str(e)}"
            ) 