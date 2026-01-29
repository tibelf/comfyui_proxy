import io
import logging
from typing import Optional, Any

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableRecordRequest,
    CreateAppTableRecordRequestBuilder,
    UpdateAppTableRecordRequest,
    UpdateAppTableRecordRequestBuilder,
    GetAppTableRecordRequest,
    GetAppTableRecordRequestBuilder,
    AppTableRecord,
    AppTableRecordBuilder,
)
from lark_oapi.api.drive.v1 import (
    UploadAllMediaRequest,
    UploadAllMediaRequestBuilder,
    UploadAllMediaRequestBodyBuilder,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


class FeishuClient:
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        settings = get_settings()
        self.app_id = app_id or settings.feishu_app_id
        self.app_secret = app_secret or settings.feishu_app_secret

        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

    async def upload_image(
        self,
        image_data: bytes,
        filename: str,
        parent_node: str,
        max_retries: int = 3,
    ) -> str:
        """
        Upload image to Feishu Drive and return the file token.
        Includes automatic retry mechanism for network instability.

        Args:
            image_data: Image bytes
            filename: Image filename
            parent_node: Parent folder token in Feishu Drive
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            File token of uploaded image
        """
        import asyncio

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                file_obj = io.BytesIO(image_data)
                request_body = UploadAllMediaRequestBodyBuilder() \
                    .file_name(filename) \
                    .parent_type("bitable_image") \
                    .parent_node(parent_node) \
                    .size(len(image_data)) \
                    .file(file_obj) \
                    .build()

                request = UploadAllMediaRequestBuilder() \
                    .request_body(request_body) \
                    .build()

                response = await self._async_request(
                    lambda: self.client.drive.v1.media.upload_all(request)
                )

                if response.success():
                    if attempt > 0:
                        logger.info(f"Upload succeeded after {attempt} retries: {filename}")
                    return response.data.file_token

                # Check if this is a retryable error
                error_msg = f"{response.code} - {response.msg}"
                last_error = RuntimeError(f"Failed to upload image: {error_msg}")

                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    logger.warning(
                        f"Upload failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Upload exception (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)

        raise last_error

    async def create_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict,
    ) -> str:
        """
        Create a new record in Feishu Bitable.

        Returns:
            Record ID of created record
        """
        record = AppTableRecordBuilder() \
            .fields(fields) \
            .build()

        request = CreateAppTableRecordRequestBuilder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(record) \
            .build()

        response = await self._async_request(
            lambda: self.client.bitable.v1.app_table_record.create(request)
        )

        if not response.success():
            raise RuntimeError(
                f"Failed to create record: {response.code} - {response.msg}"
            )

        return response.data.record.record_id

    async def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict,
    ) -> str:
        """
        Update an existing record in Feishu Bitable.

        Returns:
            Record ID of updated record
        """
        record = AppTableRecordBuilder() \
            .fields(fields) \
            .build()

        request = UpdateAppTableRecordRequestBuilder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .record_id(record_id) \
            .request_body(record) \
            .build()

        response = await self._async_request(
            lambda: self.client.bitable.v1.app_table_record.update(request)
        )

        if not response.success():
            raise RuntimeError(
                f"Failed to update record: {response.code} - {response.msg}"
            )

        return response.data.record.record_id

    async def get_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """
        Get a single record from a table.

        Args:
            app_token: Bitable app token
            table_id: Table ID
            record_id: Record ID

        Returns:
            Dictionary of field names to values
        """
        request: GetAppTableRecordRequest = (
            GetAppTableRecordRequestBuilder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(record_id)
            .build()
        )

        response = await self._async_request(
            lambda: self.client.bitable.v1.app_table_record.get(request)
        )

        if not response.success():
            logger.error(
                f"Failed to get record {record_id}: "
                f"code={response.code}, msg={response.msg}"
            )
            raise Exception(f"Failed to get record: {response.msg}")

        return response.data.record.fields

    async def upload_and_attach_images(
        self,
        app_token: str,
        table_id: str,
        image_field: str,
        images: list[tuple[bytes, str]],
        record_id: Optional[str] = None,
    ) -> tuple[str, list[str]]:
        """
        Upload images and attach them to a Bitable record.

        Args:
            app_token: Bitable app token
            table_id: Table ID
            image_field: Field name for images
            images: List of (image_data, filename) tuples
            record_id: Optional existing record ID to update

        Returns:
            Tuple of (record_id, list of file_tokens)
        """
        # Upload all images
        file_tokens = []
        for image_data, filename in images:
            # Use app_token as parent_node for bitable images
            file_token = await self.upload_image(
                image_data=image_data,
                filename=filename,
                parent_node=app_token,
            )
            file_tokens.append(file_token)
            logger.info(f"Uploaded image {filename}, token: {file_token}")

        # If updating existing record, read current images to append to them
        existing_attachments = []
        if record_id:
            try:
                existing_fields = await self.get_record(
                    app_token=app_token,
                    table_id=table_id,
                    record_id=record_id,
                )
                # Extract existing image file_tokens
                existing_images = existing_fields.get(image_field, [])
                if isinstance(existing_images, list):
                    existing_attachments = [
                        {"file_token": img["file_token"]}
                        for img in existing_images
                        if isinstance(img, dict) and "file_token" in img
                    ]
                    logger.info(
                        f"Found {len(existing_attachments)} existing images in record"
                    )
            except Exception as e:
                logger.warning(f"Failed to get existing images: {e}, will overwrite")

        # Merge existing images with new images (append logic)
        new_attachments = [{"file_token": token} for token in file_tokens]
        all_attachments = existing_attachments + new_attachments
        fields = {image_field: all_attachments}

        # Create or update record
        if record_id:
            result_record_id = await self.update_record(
                app_token=app_token,
                table_id=table_id,
                record_id=record_id,
                fields=fields,
            )
            logger.info(
                f"Updated record {record_id} with {len(new_attachments)} new images "
                f"(total: {len(all_attachments)} images)"
            )
        else:
            result_record_id = await self.create_record(
                app_token=app_token,
                table_id=table_id,
                fields=fields,
            )
            logger.info(f"Created new record {result_record_id} with {len(file_tokens)} images")

        return result_record_id, file_tokens

    async def _async_request(self, sync_func):
        """
        Execute a synchronous Feishu SDK request.
        The lark-oapi SDK is synchronous, so we run it in a thread pool.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_func)


_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """Get the global Feishu client instance"""
    global _client
    if _client is None:
        _client = FeishuClient()
    return _client
