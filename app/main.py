"""功能：创建 FastAPI 应用，装配 API 路由并在生命周期内构建依赖容器。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.bootstrap import build_container
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时构建组合根；路由通过 app.state.container 获取依赖。"""
    app.state.container = build_container(settings)
    await app.state.container.evaluation_store.initialize()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)

web_dir = Path(__file__).parent / "web"
app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    """返回比赛最小闭环演示页面。"""
    return FileResponse(web_dir / "index.html")
