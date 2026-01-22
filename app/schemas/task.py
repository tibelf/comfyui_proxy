from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class FeishuConfig(BaseModel):
    app_token: str = Field(..., description="多维表格 app_token")
    table_id: str = Field(..., description="数据表 ID")
    record_id: Optional[str] = Field(None, description="可选，更新已有记录")
    image_field: str = Field("图片", description="图片字段名")


class TaskCreateRequest(BaseModel):
    workflow: dict[str, Any] = Field(..., description="完整的 ComfyUI workflow JSON")
    output_node_ids: list[str] = Field(..., description="指定哪些节点的输出需要上传到飞书")
    feishu_config: FeishuConfig = Field(..., description="飞书配置")
    metadata: Optional[dict[str, Any]] = Field(None, description="可选，自定义元数据原样返回")


class ImageResult(BaseModel):
    node_id: str
    filename: str
    feishu_url: Optional[str] = None


class TaskResult(BaseModel):
    images: list[ImageResult] = Field(default_factory=list)
    feishu_record_id: Optional[str] = None


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = Field(0, ge=0, le=100)
    result: Optional[TaskResult] = None
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str = "Task created successfully"


class TaskDB(BaseModel):
    """Internal model for database storage"""
    task_id: str
    status: TaskStatus
    progress: int = 0
    workflow: dict[str, Any]
    output_node_ids: list[str]
    feishu_config: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
