from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from typing import List
from uuid import UUID
from fastapi import status
import logging

from ...services.upload_service import UploadService
from ...models.file import FileDB, FileUploadResponse
from ...core.config import get_settings
from ...core.deps import get_user_id_from_supabase, get_upload_service

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="The file to upload"),
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: UploadService = Depends(get_upload_service)
) -> FileUploadResponse:
    """
    Upload a file and generate embeddings.
    
    The file will be:
    1. Validated for size and type
    2. Stored in Supabase storage
    3. Processed for embeddings
    4. Indexed for search
    """
    try:
        # Log request details
        logger.info("=== File Upload Request ===")
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        logger.info(f"Content-Length: {request.headers.get('content-length')}")
        logger.info(f"User ID: {current_user_id}")
        
        # Log file details if present
        if file and hasattr(file, 'filename'):
            logger.info("File details:")
            logger.info(f"- Filename: {file.filename}")
            logger.info(f"- Content-Type: {file.content_type}")
        else:
            logger.error("No file received or file object is invalid")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No valid file received in request"
            )
            
        # Validate request content type
        content_type = request.headers.get('content-type', '')
        if not content_type.startswith('multipart/form-data'):
            logger.error(f"Invalid content type: {content_type}")
            raise HTTPException(
                status_code=415,
                detail="Request must be multipart/form-data"
            )
        
        # Log all request headers for debugging
        logger.debug("Request Headers:")
        for header, value in request.headers.items():
            logger.debug(f"- {header}: {value}")
        
        # Read and log file size
        try:
            content = await file.read()
            file_size = len(content)
            logger.info(f"- File size: {file_size} bytes")
            # Reset file position after reading
            await file.seek(0)
            
            # Check if file is empty
            if file_size == 0:
                logger.error("Empty file received")
                raise HTTPException(
                    status_code=422,
                    detail="Empty file received"
                )
                
            # Basic content validation
            try:
                # Try to decode a small sample to check if it's text
                sample = content[:1024].decode('utf-8')
                logger.debug("File content sample validation successful")
            except UnicodeDecodeError:
                logger.error("File content is not valid UTF-8 text")
                raise HTTPException(
                    status_code=422,
                    detail="File content must be valid UTF-8 text"
                )
                
        except Exception as e:
            logger.error(f"Error reading file content: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Error reading file content: {str(e)}"
            )

        # Log form data
        form = await request.form()
        logger.info("Form data keys: %s", list(form.keys()))
        
        # Process the file upload
        try:
            response = await service.save_file(file, current_user_id)
            logger.info(f"File upload successful: {response.file_id}")
            return response
        except HTTPException as he:
            logger.error(f"HTTP error in save_file: {str(he)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in save_file: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Error processing upload: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload_file endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing upload: {str(e)}"
        )

@router.get("/list", response_model=List[FileDB])
async def list_files(
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: UploadService = Depends(get_upload_service)
) -> List[FileDB]:
    """List all files uploaded by the current user."""
    return await service.get_user_files(current_user_id)

@router.get("/{file_id}/content")
async def get_file_content(
    file_id: UUID,
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: UploadService = Depends(get_upload_service)
) -> str:
    """Get the content of a specific file."""
    return await service.get_file_content(file_id, current_user_id)

@router.get("/count")
async def count_files(
    current_user_id: UUID = Depends(get_user_id_from_supabase),
    service: UploadService = Depends(get_upload_service)
) -> dict:
    """Get the total number of files for the current user."""
    try:
        # Get all files without limit
        response = service.supabase.table('files')\
            .select('id', count='exact')\
            .eq('user_id', str(current_user_id))\
            .execute()
        
        return {"count": response.count or 0}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to count files: {str(e)}"
        ) 