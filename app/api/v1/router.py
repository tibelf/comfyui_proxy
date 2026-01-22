from fastapi import APIRouter

from app.api.v1.tasks import router as tasks_router
from app.api.v1.health import router as health_router

router = APIRouter(prefix="/api/v1")

router.include_router(tasks_router)
router.include_router(health_router)
