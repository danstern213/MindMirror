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
        try:
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            logger.info(f"Checking file extension: {ext} for file: {filename}")
            
            if not ext:
                logger.error(f"No file extension found for file: {filename}")
                raise HTTPException(
                    status_code=422,
                    detail="File must have an extension"
                )
                
            if ext not in settings.ALLOWED_EXTENSIONS:
                logger.error(f"Invalid file extension: {ext}. Allowed: {settings.ALLOWED_EXTENSIONS}")
                raise HTTPException(
                    status_code=415,
                    detail=f"File extension .{ext} not allowed. Allowed extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}"
                )
                
            logger.info(f"File extension {ext} is allowed")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking file extension for {filename}: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Invalid filename or extension: {str(e)}"
            )

    async def save_file(
        self,
        file: UploadFile,
        user_id: UUID,
        api_key: Optional[str] = None
    ) -> FileUploadResponse:
        """Save file to storage and generate embeddings."""
        try:
            logger.info(f"Starting file upload process for: {file.filename}")
            logger.info(f"User ID: {user_id}")
            
            # Validate file
            content = await file.read()
            content_size = len(content)
            logger.info(f"File size: {content_size} bytes")
            
            try:
                self._check_file_size(content_size)
                logger.info("File size validation passed")
            except HTTPException as e:
                logger.error(f"File size validation failed: {str(e)}")
                raise

            try:
                self._check_file_extension(file.filename)
                logger.info("File extension validation passed")
            except HTTPException as e:
                logger.error(f"File extension validation failed: {str(e)}")
                raise
            
            # Create unique filename
            file_id = uuid4()
            sanitized_filename = self._sanitize_filename(file.filename)
            storage_path = f"{user_id}/{file_id}/{sanitized_filename}"
            logger.info(f"Generated storage path: {storage_path}")

            # Upload to Supabase storage
            logger.info("Attempting to upload to Supabase storage")
            try:
                storage_response = self.supabase.storage.from_('documents').upload(
                    storage_path,
                    content
                )

                if hasattr(storage_response, 'error') and storage_response.error:
                    logger.error(f"Supabase storage error: {storage_response.error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error uploading file: {storage_response.error['message']}"
                    )
                logger.info("Successfully uploaded to Supabase storage")
            except Exception as e:
                logger.error(f"Failed to upload to Supabase storage: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload to storage: {str(e)}"
                )

            # Save file metadata
            logger.info("Saving file metadata")
            file_data = FileCreate(
                filename=file.filename,
                storage_path=storage_path,
                title=file.filename,
                user_id=user_id,
                status='pending_embedding'
            )

            try:
                # Convert model to dict and ensure UUIDs are converted to strings
                metadata = file_data.model_dump()
                metadata['user_id'] = str(metadata['user_id'])  # Convert UUID to string
                
                file_response = self.supabase.table('files').insert(metadata).execute()

                if hasattr(file_response, 'error') and file_response.error:
                    logger.error(f"Database error saving metadata: {file_response.error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error saving file metadata: {file_response.error['message']}"
                    )
                logger.info("Successfully saved file metadata")
            except Exception as e:
                logger.error(f"Failed to save file metadata: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save file metadata: {str(e)}"
                )

            file_record = FileDB(**file_response.data[0])

            # Generate embeddings asynchronously
            logger.info("Starting embedding generation")
            try:
                text_content = content.decode('utf-8')
                await self.embedding_service.generate_and_save_embedding(
                    text_content,
                    str(file_record.id),
                    str(user_id),
                    api_key
                )
                logger.info("Successfully generated embeddings")
            except UnicodeDecodeError as e:
                logger.error(f"Failed to decode file content: {str(e)}")
                raise HTTPException(
                    status_code=422,
                    detail="File content must be valid UTF-8 text"
                )
            except Exception as e:
                logger.error(f"Failed to generate embeddings: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate embeddings: {str(e)}"
                )

            # Update file status
            try:
                self.supabase.table('files').update({
                    'status': 'indexed'
                }).eq('id', file_record.id).execute()
                logger.info("Successfully updated file status to indexed")
            except Exception as e:
                logger.error(f"Failed to update file status: {str(e)}")
                # Non-critical error, don't raise

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
            logger.error(f"Unexpected error processing file {file.filename}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred while processing the file: {str(e)}"
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