"""功能：创建 FastAPI 应用，装配 API 路由并在生命周期内构建依赖容器。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.v1.router import api_router
from app.bootstrap import build_container
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时构建组合根；路由通过 app.state.container 获取依赖。"""
    app.state.container = build_container(settings)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """将服务根地址引导到可交互的 API 文档。"""
    return RedirectResponse(url="/docs")
