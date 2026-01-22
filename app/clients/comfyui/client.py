import asyncio
import json
import uuid
import logging
from typing import Any, Callable, Optional

import httpx
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)


class ComfyUIClient:
    def __init__(self):
        settings = get_settings()
        self.http_url = settings.comfyui_http_url
        self.ws_url = settings.comfyui_ws_url
        self.client_id = str(uuid.uuid4())

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Queue a workflow prompt and return the prompt_id"""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.http_url}/prompt",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        """Get execution history for a prompt"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.http_url}/history/{prompt_id}")
            response.raise_for_status()
            return response.json()

    async def get_image(
        self,
        filename: str,
        subfolder: str = "",
        folder_type: str = "output",
    ) -> bytes:
        """Get image data from ComfyUI"""
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.http_url}/view",
                params=params,
            )
            response.raise_for_status()
            return response.content

    async def wait_for_completion(
        self,
        prompt_id: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """
        Wait for workflow completion via WebSocket.
        Returns the execution outputs when done.
        """
        ws_url = f"{self.ws_url}?clientId={self.client_id}"

        async with websockets.connect(ws_url) as ws:
            start_time = asyncio.get_event_loop().time()

            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"Workflow execution timed out after {timeout}s")

                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    data = json.loads(message)

                    msg_type = data.get("type")

                    if msg_type == "progress":
                        msg_data = data.get("data", {})
                        if msg_data.get("prompt_id") == prompt_id:
                            value = msg_data.get("value", 0)
                            max_value = msg_data.get("max", 100)
                            progress = int((value / max_value) * 100) if max_value > 0 else 0
                            if progress_callback:
                                progress_callback(progress)

                    elif msg_type == "executing":
                        msg_data = data.get("data", {})
                        if msg_data.get("prompt_id") == prompt_id:
                            if msg_data.get("node") is None:
                                # Execution completed
                                break

                    elif msg_type == "execution_error":
                        msg_data = data.get("data", {})
                        if msg_data.get("prompt_id") == prompt_id:
                            error_msg = msg_data.get("exception_message", "Unknown error")
                            raise RuntimeError(f"ComfyUI execution error: {error_msg}")

                except asyncio.TimeoutError:
                    # WebSocket recv timeout, continue waiting
                    continue

        # Get the execution result from history
        history = await self.get_history(prompt_id)
        if prompt_id not in history:
            raise RuntimeError(f"Prompt {prompt_id} not found in history")

        return history[prompt_id]

    async def get_outputs_for_nodes(
        self,
        history: dict[str, Any],
        node_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Extract output images for specified node IDs from execution history.
        Returns list of image info dicts with node_id, filename, subfolder, type.
        """
        outputs = history.get("outputs", {})
        images = []

        for node_id in node_ids:
            if node_id not in outputs:
                logger.warning(f"Node {node_id} not found in outputs")
                continue

            node_output = outputs[node_id]
            node_images = node_output.get("images", [])

            for img in node_images:
                images.append({
                    "node_id": node_id,
                    "filename": img.get("filename"),
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })

        return images

    async def check_health(self) -> bool:
        """Check if ComfyUI is reachable"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.http_url}/system_stats",
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False


_client: Optional[ComfyUIClient] = None


def get_comfyui_client() -> ComfyUIClient:
    """Get the global ComfyUI client instance"""
    global _client
    if _client is None:
        _client = ComfyUIClient()
    return _client
