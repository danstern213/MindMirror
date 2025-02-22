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
from io import BytesIO
from PyPDF2 import PdfReader
import docx

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

    def _extract_text_from_pdf(self, content: bytes) -> str:
        """Extract text from PDF content."""
        try:
            pdf_file = BytesIO(content)
            pdf_reader = PdfReader(pdf_file)
            text = []
            for page in pdf_reader.pages:
                text.append(page.extract_text())
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Error extracting text from PDF: {str(e)}"
            )

    def _extract_text_from_docx(self, content: bytes) -> str:
        """Extract text from DOCX content."""
        try:
            docx_file = BytesIO(content)
            doc = docx.Document(docx_file)
            text = []
            for paragraph in doc.paragraphs:
                if paragraph.text:
                    text.append(paragraph.text)
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Error extracting text from DOCX: {str(e)}"
            )

    def _extract_text_from_binary(self, content: bytes, filename: str) -> str:
        """Extract text from binary file formats."""
        ext = filename.lower().split('.')[-1]
        if ext == 'pdf':
            return self._extract_text_from_pdf(content)
        elif ext in ['docx', 'doc']:
            return self._extract_text_from_docx(content)
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported binary file format: .{ext}"
            )

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

    async def _check_duplicate_file(self, filename: str, user_id: UUID) -> Optional[FileDB]:
        """
        Check if a file with the same name exists for the user.
        Returns None if no duplicate exists or if the existing file needs processing
        (status is 'error' or 'pending_embedding').
        """
        try:
            response = self.supabase.table('files')\
                .select('*')\
                .eq('user_id', str(user_id))\
                .eq('filename', filename)\
                .execute()

            if hasattr(response, 'error') and response.error:
                logger.error(f"Error checking for duplicate file: {response.error}")
                return None

            if response.data:
                existing_file = FileDB(**response.data[0])
                # Allow re-upload if the previous upload had errors or never completed embedding
                if existing_file.status in ['error', 'pending_embedding']:
                    logger.info(f"Found existing file {filename} with status {existing_file.status}, allowing re-upload")
                    # Delete the old file record since we'll create a new one
                    try:
                        # Delete from storage first
                        self.supabase.storage.from_('documents')\
                            .remove([existing_file.storage_path])
                        logger.info(f"Deleted old file from storage: {existing_file.storage_path}")
                        
                        # Then delete the database record
                        self.supabase.table('files')\
                            .delete()\
                            .eq('id', existing_file.id)\
                            .execute()
                        logger.info(f"Deleted old file record from database: {existing_file.id}")
                    except Exception as e:
                        logger.error(f"Error cleaning up old file: {str(e)}")
                    return None
                return existing_file
            return None
        except Exception as e:
            logger.error(f"Error checking for duplicate file: {str(e)}")
            return None

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
            
            # Check for duplicate file
            existing_file = await self._check_duplicate_file(file.filename, user_id)
            if existing_file:
                logger.info(f"Duplicate file found: {file.filename} with status: {existing_file.status}")
                return FileUploadResponse(
                    file_id=existing_file.id,
                    filename=existing_file.filename,
                    upload_time=existing_file.created_at,
                    status="skipped",
                    embedding_status="skipped_duplicate"
                )
            
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
                status='pending_embedding' if content_size > 0 else 'empty'
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
            embedding_status = "skipped_empty"

            # Generate embeddings asynchronously only if file is not empty
            if content_size > 0:
                logger.info("Starting embedding generation")
                try:
                    # Handle binary files (PDF, DOCX)
                    ext = file.filename.lower().split('.')[-1]
                    if ext in ['pdf', 'docx', 'doc']:
                        text_content = self._extract_text_from_binary(content, file.filename)
                    else:
                        try:
                            text_content = content.decode('utf-8')
                        except UnicodeDecodeError:
                            logger.error("Failed to decode file content as UTF-8")
                            raise HTTPException(
                                status_code=422,
                                detail="File content must be valid UTF-8 text"
                            )

                    try:
                        await self.embedding_service.generate_and_save_embedding(
                            text_content,
                            str(file_record.id),
                            str(user_id),
                            api_key
                        )
                        logger.info("Successfully generated embeddings")
                        embedding_status = "completed"
                        
                        # Update file status to indexed
                        try:
                            self.supabase.table('files').update({
                                'status': 'indexed'
                            }).eq('id', file_record.id).execute()
                            logger.info("Successfully updated file status to indexed")
                        except Exception as e:
                            logger.error(f"Failed to update file status: {str(e)}")
                    except ValueError as ve:
                        if "Invalid isoformat string" in str(ve):
                            logger.warning(f"Date format error during embedding generation: {str(ve)}")
                            embedding_status = "error_date_format"
                            # Continue processing despite date format error
                            self.supabase.table('files').update({
                                'status': 'indexed'
                            }).eq('id', file_record.id).execute()
                        else:
                            embedding_status = "error"
                            logger.error(f"Embedding generation failed: {str(ve)}")
                    except Exception as e:
                        embedding_status = "error"
                        logger.error(f"Failed to generate embeddings: {str(e)}")
                        # Update file status to error but don't fail the upload
                        self.supabase.table('files').update({
                            'status': 'error'
                        }).eq('id', file_record.id).execute()
                except Exception as e:
                    embedding_status = "error"
                    logger.error(f"Failed to process file content: {str(e)}")
                    self.supabase.table('files').update({
                        'status': 'error'
                    }).eq('id', file_record.id).execute()

            return FileUploadResponse(
                file_id=file_record.id,
                filename=file_record.filename,
                upload_time=file_record.created_at,
                status="success",
                embedding_status=embedding_status
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