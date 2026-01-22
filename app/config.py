from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ComfyUI Configuration
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = 8188

    # Feishu Configuration
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    # Storage Configuration
    sqlite_database: str = "./data/tasks.db"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @property
    def comfyui_http_url(self) -> str:
        return f"http://{self.comfyui_host}:{self.comfyui_port}"

    @property
    def comfyui_ws_url(self) -> str:
        return f"ws://{self.comfyui_host}:{self.comfyui_port}/ws"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
