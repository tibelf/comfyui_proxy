from fastapi import APIRouter
from pydantic import BaseModel

from app.clients.comfyui.client import get_comfyui_client

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    comfyui_available: bool


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns service status and ComfyUI availability.
    """
    comfyui_client = get_comfyui_client()
    comfyui_available = await comfyui_client.check_health()

    return HealthResponse(
        status="healthy",
        comfyui_available=comfyui_available,
    )
