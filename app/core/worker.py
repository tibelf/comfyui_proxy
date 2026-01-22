import asyncio
import logging
from typing import Optional

from app.schemas.task import TaskStatus, TaskResult, ImageResult, FeishuConfig
from app.core.task_manager import get_task_manager
from app.clients.comfyui.client import get_comfyui_client
from app.clients.feishu.client import get_feishu_client

logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background worker"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Background worker started")

    async def stop(self):
        """Stop the background worker"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Background worker stopped")

    async def _run(self):
        """Main worker loop"""
        while self._running:
            try:
                await self._process_pending_tasks()
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _process_pending_tasks(self):
        """Process pending tasks"""
        task_manager = get_task_manager()
        pending_tasks = await task_manager.get_pending_tasks(limit=1)

        for task in pending_tasks:
            try:
                await self._process_task(task.task_id)
            except Exception as e:
                logger.exception(f"Error processing task {task.task_id}: {e}")
                await task_manager.fail_task(task.task_id, str(e))

    async def _process_task(self, task_id: str):
        """Process a single task"""
        task_manager = get_task_manager()
        comfyui_client = get_comfyui_client()
        feishu_client = get_feishu_client()

        # Get task details
        task = await task_manager.get_task(task_id)
        if task is None:
            logger.warning(f"Task {task_id} not found")
            return

        logger.info(f"Processing task {task_id}")

        # Update status to processing
        await task_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.PROCESSING,
            progress=0,
        )

        # Get task data from storage
        from app.storage.sqlite import get_storage
        storage = await get_storage()
        task_db = await storage.get_task(task_id)

        if task_db is None:
            raise RuntimeError(f"Task {task_id} not found in storage")

        # Queue the workflow
        prompt_id = await comfyui_client.queue_prompt(task_db.workflow)
        logger.info(f"Task {task_id}: Queued prompt {prompt_id}")

        # Wait for completion with progress callback
        async def update_progress(progress: int):
            await task_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.PROCESSING,
                progress=progress,
            )

        # Use sync callback wrapper for the async update
        last_progress = [0]

        def progress_callback(progress: int):
            last_progress[0] = progress
            # Note: We can't await here, but the progress is also updated after completion

        history = await comfyui_client.wait_for_completion(
            prompt_id=prompt_id,
            progress_callback=progress_callback,
        )

        logger.info(f"Task {task_id}: Workflow completed")

        # Extract outputs for specified nodes
        outputs = await comfyui_client.get_outputs_for_nodes(
            history=history,
            node_ids=task_db.output_node_ids,
        )

        if not outputs:
            raise RuntimeError("No output images found for specified nodes")

        logger.info(f"Task {task_id}: Found {len(outputs)} output images")

        # Update status to uploading
        await task_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.UPLOADING,
            progress=80,
        )

        # Download images from ComfyUI
        images_data = []
        for output in outputs:
            image_data = await comfyui_client.get_image(
                filename=output["filename"],
                subfolder=output["subfolder"],
                folder_type=output["type"],
            )
            images_data.append((image_data, output["filename"], output["node_id"]))

        logger.info(f"Task {task_id}: Downloaded {len(images_data)} images")

        # Upload to Feishu
        feishu_config = FeishuConfig(**task_db.feishu_config)

        images_for_upload = [(data, filename) for data, filename, _ in images_data]

        record_id, file_tokens = await feishu_client.upload_and_attach_images(
            app_token=feishu_config.app_token,
            table_id=feishu_config.table_id,
            image_field=feishu_config.image_field,
            images=images_for_upload,
            record_id=feishu_config.record_id,
        )

        logger.info(f"Task {task_id}: Uploaded to Feishu record {record_id}")

        # Build result
        image_results = []
        for i, (data, filename, node_id) in enumerate(images_data):
            image_results.append(ImageResult(
                node_id=node_id,
                filename=filename,
                feishu_url=None,  # File tokens don't have direct URLs
            ))

        result = TaskResult(
            images=image_results,
            feishu_record_id=record_id,
        )

        # Mark as completed
        await task_manager.complete_task(task_id, result)
        logger.info(f"Task {task_id}: Completed successfully")


_worker: Optional[BackgroundWorker] = None


def get_worker() -> BackgroundWorker:
    """Get the global background worker instance"""
    global _worker
    if _worker is None:
        _worker = BackgroundWorker()
    return _worker


async def start_worker():
    """Start the global background worker"""
    worker = get_worker()
    await worker.start()


async def stop_worker():
    """Stop the global background worker"""
    global _worker
    if _worker:
        await _worker.stop()
        _worker = None
