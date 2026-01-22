#!/bin/bash
# ComfyUI Proxy 启动脚本

set -e

CONTAINER_NAME="comfyui_proxy-comfyui-proxy-1"

echo "Starting ComfyUI Proxy..."

# 启动容器
docker compose up -d --build

# 等待容器启动
sleep 2

# 连接到默认 bridge 网络（解决飞书 SSL 问题）
if docker network inspect bridge | grep -q "$CONTAINER_NAME"; then
    echo "Already connected to bridge network"
else
    echo "Connecting to bridge network..."
    docker network connect bridge "$CONTAINER_NAME"
fi

echo "ComfyUI Proxy started successfully!"
echo "API available at: http://localhost:8000"
