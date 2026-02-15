from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from typing import List
from uuid import UUID
from fastapi import status
import logging
import traceback

from ...services.upload_service import UploadService
from ...models.file import FileDB, FileUploadResponse
from ...core.config import get_settings
from ...core.deps import get_user_id_from_supabase, get_user_id_from_auth, get_upload_service

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="The file to upload"),
    current_user_id: UUID = Depends(get_user_id_from_auth),
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
        content = None
        try:
            content = await file.read()
            file_size = len(content)
            logger.info(f"- File size: {file_size} bytes")
            # Reset file position after reading
            await file.seek(0)
            
            # Check if file is empty
            if file_size == 0:
                logger.info("Empty file received, will process with empty content flag")
            
            # Skip UTF-8 validation for binary files (PDF, DOCX)
            ext = file.filename.lower().split('.')[-1]
            if ext not in ['pdf', 'docx', 'doc']:
                # Basic content validation for non-binary files
                try:
                    # Only try to decode content if file is not empty
                    if file_size > 0:
                        # Try to decode a small sample to check if it's text
                        sample = content[:1024].decode('utf-8')
                        logger.debug("File content sample validation successful")
                    else:
                        logger.debug("Skipping content validation for empty file")
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
        finally:
            # Clear content after validation
            if content:
                del content

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
        finally:
            # Ensure file is closed
            await file.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload_file endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing upload: {str(e)}"
        )

@router.put("/replace", response_model=FileUploadResponse)
async def replace_file(
    request: Request,
    file: UploadFile = File(..., description="The file to replace"),
    current_user_id: UUID = Depends(get_user_id_from_auth),
    service: UploadService = Depends(get_upload_service)
) -> FileUploadResponse:
    """
    Replace an existing file with a new version.

    This endpoint:
    1. Deletes any existing file with the same name (including embeddings)
    2. Uploads the new file
    3. Generates new embeddings

    Supports both JWT token and API key authentication.
    If no existing file is found, performs a normal upload.
    """
    try:
        logger.info("=== File Replace Request ===")
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        logger.info(f"User ID: {current_user_id}")

        if file and hasattr(file, 'filename'):
            logger.info(f"File details: {file.filename}")
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No valid file received in request"
            )

        content_type = request.headers.get('content-type', '')
        if not content_type.startswith('multipart/form-data'):
            raise HTTPException(
                status_code=415,
                detail="Request must be multipart/form-data"
            )

        # Validate file content
        content = await file.read()
        file_size = len(content)
        logger.info(f"File size: {file_size} bytes")
        await file.seek(0)

        ext = file.filename.lower().split('.')[-1]
        if ext not in ['pdf', 'docx', 'doc'] and file_size > 0:
            try:
                content[:1024].decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=422,
                    detail="File content must be valid UTF-8 text"
                )

        del content

        # Get API key for embedding service if present
        api_key = request.headers.get('X-API-Key')

        try:
            response = await service.replace_file(file, current_user_id, api_key)
            logger.info(f"File replace successful: {response.file_id}")
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in replace_file: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Error processing replace: {str(e)}"
            )
        finally:
            await file.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in replace_file endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing replace: {str(e)}"
        )


@router.get("/list", response_model=List[FileDB])
async def list_files(
    current_user_id: UUID = Depends(get_user_id_from_auth),
    service: UploadService = Depends(get_upload_service)
) -> List[FileDB]:
    """List all files uploaded by the current user. Supports both JWT and API key auth."""
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
        logger.info(f"Counting files for user: {current_user_id}")
        
        # Verify Supabase connection
        if not service.supabase:
            logger.error("Supabase client not initialized")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection not initialized"
            )
            
        # Log the query we're about to make
        logger.info(f"Querying files table for user_id: {str(current_user_id)}")
        
        # Get all files without limit
        response = service.supabase.table('files')\
            .select('id', count='exact')\
            .eq('user_id', str(current_user_id))\
            .execute()
            
        logger.info(f"Query response: {response}")
        
        return {"count": response.count or 0}
    except Exception as e:
        logger.error(f"Failed to count files: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to count files: {str(e)}"
        ) 