import uuid
from datetime import datetime
from typing import Optional

from app.schemas.task import (
    TaskDB,
    TaskStatus,
    TaskCreateRequest,
    TaskResponse,
    TaskResult,
)
from app.storage.sqlite import get_storage


class TaskManager:
    async def create_task(self, request: TaskCreateRequest) -> TaskDB:
        """Create a new task from request"""
        storage = await get_storage()

        task = TaskDB(
            task_id=str(uuid.uuid4()),
            status=TaskStatus.PENDING,
            progress=0,
            workflow=request.workflow,
            output_node_ids=request.output_node_ids,
            feishu_config=request.feishu_config.model_dump(),
            result=None,
            error=None,
            metadata=request.metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        return await storage.create_task(task)

    async def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """Get task status by ID"""
        storage = await get_storage()
        task = await storage.get_task(task_id)

        if task is None:
            return None

        return self._to_response(task)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task"""
        storage = await get_storage()
        task = await storage.get_task(task_id)

        if task is None:
            return False

        # Only pending tasks can be cancelled
        if task.status != TaskStatus.PENDING:
            return False

        await storage.delete_task(task_id)
        return True

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
    ) -> Optional[TaskDB]:
        """Update task status"""
        storage = await get_storage()
        return await storage.update_task(
            task_id=task_id,
            status=status,
            progress=progress,
        )

    async def complete_task(
        self,
        task_id: str,
        result: TaskResult,
    ) -> Optional[TaskDB]:
        """Mark task as completed with result"""
        storage = await get_storage()
        return await storage.update_task(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            result=result.model_dump(),
        )

    async def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> Optional[TaskDB]:
        """Mark task as failed with error"""
        storage = await get_storage()
        return await storage.update_task(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=error,
        )

    async def get_pending_tasks(self, limit: int = 10) -> list[TaskDB]:
        """Get pending tasks for processing"""
        storage = await get_storage()
        return await storage.get_pending_tasks(limit)

    def _to_response(self, task: TaskDB) -> TaskResponse:
        """Convert TaskDB to TaskResponse"""
        result = None
        if task.result:
            result = TaskResult(**task.result)

        return TaskResponse(
            task_id=task.task_id,
            status=task.status,
            progress=task.progress,
            result=result,
            error=task.error,
            metadata=task.metadata,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
