# ComfyUI Proxy Service

ComfyUI 请求代理服务，接收 n8n 工作流请求，异步生成图片并上传到飞书多维表格，支持任务状态轮询。

## 功能特点

- 接收完整的 ComfyUI workflow JSON，通用性强
- 异步任务处理，支持状态轮询
- 自动上传生成图片到飞书多维表格
- SQLite 持久化任务状态
- Docker 部署支持

## 项目结构

```
comfyui_proxy/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置管理
│   ├── api/v1/
│   │   ├── tasks.py             # 任务接口
│   │   └── health.py            # 健康检查
│   ├── core/
│   │   ├── task_manager.py      # 任务管理
│   │   └── worker.py            # 后台处理
│   ├── clients/
│   │   ├── comfyui/client.py    # ComfyUI 客户端
│   │   └── feishu/client.py     # 飞书客户端
│   ├── storage/
│   │   └── sqlite.py            # SQLite 存储
│   └── schemas/
│       └── task.py              # 数据模型
├── workflows/                    # 示例工作流
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 安装

### 本地运行

```bash
# 克隆项目
git clone <repo-url>
cd comfyui_proxy

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 启动服务
uvicorn app.main:app --reload
```

### Docker 部署

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 配置

在 `.env` 文件中配置以下环境变量：

```bash
# ComfyUI 配置
COMFYUI_HOST=127.0.0.1       # ComfyUI 服务地址
COMFYUI_PORT=8188            # ComfyUI 服务端口

# 飞书配置
FEISHU_APP_ID=xxx            # 飞书应用 App ID
FEISHU_APP_SECRET=xxx        # 飞书应用 App Secret

# 存储配置
SQLITE_DATABASE=./data/tasks.db

# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

## API 接口

### 提交任务

```http
POST /api/v1/tasks
Content-Type: application/json
```

请求体：

```json
{
  "workflow": {
    "3": {
      "inputs": { ... },
      "class_type": "KSampler"
    },
    ...
  },
  "output_node_ids": ["9"],
  "feishu_config": {
    "app_token": "xxx",
    "table_id": "xxx",
    "record_id": "xxx",
    "image_field": "图片"
  },
  "metadata": {
    "custom_key": "custom_value"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| workflow | object | 是 | 完整的 ComfyUI workflow JSON |
| output_node_ids | string[] | 是 | 需要上传的输出节点 ID 列表 |
| feishu_config.app_token | string | 是 | 飞书多维表格 app_token |
| feishu_config.table_id | string | 是 | 数据表 ID |
| feishu_config.record_id | string | 否 | 已有记录 ID，用于更新 |
| feishu_config.image_field | string | 是 | 图片字段名 |
| metadata | object | 否 | 自定义元数据，原样返回 |

响应：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Task created successfully"
}
```

### 查询任务状态

```http
GET /api/v1/tasks/{task_id}
```

响应：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "result": {
    "images": [
      {
        "node_id": "9",
        "filename": "ComfyUI_00001_.png",
        "feishu_url": null
      }
    ],
    "feishu_record_id": "recXXXXXX"
  },
  "error": null,
  "metadata": {},
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:01:00"
}
```

任务状态：

| 状态 | 说明 |
|------|------|
| pending | 等待处理 |
| processing | ComfyUI 处理中 |
| uploading | 上传飞书中 |
| completed | 已完成 |
| failed | 失败 |

### 取消任务

```http
DELETE /api/v1/tasks/{task_id}
```

仅 `pending` 状态的任务可取消。

### 健康检查

```http
GET /api/v1/health
```

响应：

```json
{
  "status": "healthy",
  "comfyui_available": true
}
```

## 使用示例

### cURL

```bash
# 提交任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": '"$(cat workflows/txt2img_basic.json)"',
    "output_node_ids": ["9"],
    "feishu_config": {
      "app_token": "your_app_token",
      "table_id": "your_table_id",
      "image_field": "图片"
    }
  }'

# 查询状态
curl http://localhost:8000/api/v1/tasks/{task_id}

# 健康检查
curl http://localhost:8000/api/v1/health
```

### Python

```python
import httpx
import json
import time

BASE_URL = "http://localhost:8000"

# 读取 workflow
with open("workflows/txt2img_basic.json") as f:
    workflow = json.load(f)

# 提交任务
response = httpx.post(f"{BASE_URL}/api/v1/tasks", json={
    "workflow": workflow,
    "output_node_ids": ["9"],
    "feishu_config": {
        "app_token": "your_app_token",
        "table_id": "your_table_id",
        "image_field": "图片"
    }
})
task_id = response.json()["task_id"]
print(f"Task created: {task_id}")

# 轮询状态
while True:
    response = httpx.get(f"{BASE_URL}/api/v1/tasks/{task_id}")
    data = response.json()
    print(f"Status: {data['status']}, Progress: {data['progress']}%")

    if data["status"] in ["completed", "failed"]:
        break

    time.sleep(2)

# 输出结果
if data["status"] == "completed":
    print(f"Record ID: {data['result']['feishu_record_id']}")
    for img in data["result"]["images"]:
        print(f"  - {img['filename']}")
else:
    print(f"Error: {data['error']}")
```

### n8n 集成

在 n8n 中使用 HTTP Request 节点：

1. **提交任务**
   - Method: POST
   - URL: `http://your-server:8000/api/v1/tasks`
   - Body: JSON with workflow and feishu_config

2. **轮询状态**
   - 使用 Loop 节点配合 HTTP Request
   - Method: GET
   - URL: `http://your-server:8000/api/v1/tasks/{{ $json.task_id }}`
   - 检查 status 字段直到 completed 或 failed

## 飞书配置

1. 在[飞书开放平台](https://open.feishu.cn/)创建应用
2. 获取 App ID 和 App Secret
3. 开通以下权限：
   - `bitable:app:readonly` - 读取多维表格
   - `bitable:app` - 编辑多维表格
   - `drive:drive` - 上传文件到云空间
4. 将应用添加为多维表格协作者

## 注意事项

- ComfyUI 需要已启动并可访问
- workflow JSON 需要是 API 格式（从 ComfyUI 导出）
- output_node_ids 必须是 SaveImage 类型节点的 ID
- 飞书应用需要有多维表格的编辑权限

## License

MIT
