from fastapi import APIRouter, HTTPException, status

from app.schemas.task import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskResponse,
    TaskStatus,
)
from app.core.task_manager import get_task_manager

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(request: TaskCreateRequest):
    """
    Submit a new ComfyUI workflow task.

    The task will be processed asynchronously. Use the returned task_id
    to poll for status updates.
    """
    task_manager = get_task_manager()
    task = await task_manager.create_task(request)

    return TaskCreateResponse(
        task_id=task.task_id,
        status=task.status,
        message="Task created successfully",
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
)
async def get_task(task_id: str):
    """
    Get the status and result of a task.

    Poll this endpoint to track task progress.
    """
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_task(task_id: str):
    """
    Cancel a pending task.

    Only tasks in 'pending' status can be cancelled.
    Tasks that are already processing cannot be cancelled.
    """
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    if task.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel task in '{task.status}' status. Only pending tasks can be cancelled.",
        )

    success = await task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel task",
        )

    return None
