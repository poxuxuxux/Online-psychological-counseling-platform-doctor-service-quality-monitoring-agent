"""功能：创建 FastAPI 应用并装配 API 路由；后续在此处接入应用生命周期和依赖容器。"""

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(api_router)
