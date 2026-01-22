import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.api.v1.router import router as api_router
from app.storage.sqlite import init_storage, close_storage
from app.core.worker import start_worker, stop_worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    settings = get_settings()

    # Startup
    logger.info("Starting ComfyUI Proxy Service...")

    # Initialize storage
    await init_storage(settings.sqlite_database)
    logger.info(f"Initialized SQLite storage at {settings.sqlite_database}")

    # Start background worker
    await start_worker()
    logger.info("Started background worker")

    logger.info("ComfyUI Proxy Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down ComfyUI Proxy Service...")

    # Stop background worker
    await stop_worker()
    logger.info("Stopped background worker")

    # Close storage
    await close_storage()
    logger.info("Closed storage")

    logger.info("ComfyUI Proxy Service shut down successfully")


app = FastAPI(
    title="ComfyUI Proxy Service",
    description="Proxy service for ComfyUI workflows with Feishu integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Include API router
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ComfyUI Proxy Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
