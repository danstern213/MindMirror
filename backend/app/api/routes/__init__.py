from fastapi import APIRouter
from .files import router as files_router
from .search import router as search_router
from .embeddings import router as embeddings_router
from .storage import router as storage_router
from .chat import router as chat_router
from .settings import router as settings_router
from .api_keys import router as api_keys_router

router = APIRouter()

router.include_router(files_router, prefix="/files", tags=["files"])
router.include_router(search_router, prefix="/search", tags=["search"])
router.include_router(embeddings_router, prefix="/embeddings", tags=["embeddings"])
router.include_router(storage_router, prefix="/storage", tags=["storage"])
router.include_router(chat_router, prefix="/chat", tags=["chat"])
router.include_router(settings_router, prefix="/settings", tags=["settings"])
router.include_router(api_keys_router, prefix="/api-keys", tags=["api-keys"]) 