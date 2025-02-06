from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from typing import List
from uuid import UUID
from fastapi import status

from ...services.upload_service import UploadService
from ...models.file import FileDB, FileUploadResponse
from ...core.config import get_settings
from ...core.deps import get_user_id_from_supabase, get_upload_service

router = APIRouter()
settings = get_settings()

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
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
    return await service.save_file(file, current_user_id)

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