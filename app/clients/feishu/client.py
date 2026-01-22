import logging
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableRecordRequest,
    CreateAppTableRecordRequestBuilder,
    UpdateAppTableRecordRequest,
    UpdateAppTableRecordRequestBuilder,
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
    ) -> str:
        """
        Upload image to Feishu Drive and return the file token.

        Args:
            image_data: Image bytes
            filename: Image filename
            parent_node: Parent folder token in Feishu Drive

        Returns:
            File token of uploaded image
        """
        request_body = UploadAllMediaRequestBodyBuilder() \
            .file_name(filename) \
            .parent_type("bitable_image") \
            .parent_node(parent_node) \
            .size(len(image_data)) \
            .file(image_data) \
            .build()

        request = UploadAllMediaRequestBuilder() \
            .request_body(request_body) \
            .build()

        response = await self._async_request(
            lambda: self.client.drive.v1.media.upload_all(request)
        )

        if not response.success():
            raise RuntimeError(
                f"Failed to upload image: {response.code} - {response.msg}"
            )

        return response.data.file_token

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

        # Prepare attachment field value
        attachments = [{"file_token": token} for token in file_tokens]
        fields = {image_field: attachments}

        # Create or update record
        if record_id:
            result_record_id = await self.update_record(
                app_token=app_token,
                table_id=table_id,
                record_id=record_id,
                fields=fields,
            )
        else:
            result_record_id = await self.create_record(
                app_token=app_token,
                table_id=table_id,
                fields=fields,
            )

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
