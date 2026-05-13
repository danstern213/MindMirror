from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import AsyncGenerator
from uuid import UUID
import json
import logging

from ...services.briefing_service import BriefingService
from ...core.deps import get_user_id_from_auth, get_briefing_service

router = APIRouter()
logger = logging.getLogger(__name__)


class BriefingRequest(BaseModel):
    user_id: UUID


@router.post("/generate")
async def generate_briefing(
    request: BriefingRequest,
    current_user_id: UUID = Depends(get_user_id_from_auth),
    service: BriefingService = Depends(get_briefing_service),
) -> StreamingResponse:
    """Generate and stream a personalized daily briefing from the user's notes."""
    if request.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to generate briefing for other users"
        )

    async def stream_response() -> AsyncGenerator[str, None]:
        try:
            async for text in service.generate(current_user_id):
                yield f"data: {json.dumps({'content': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error generating briefing: {e}", exc_info=True)
            raise

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
