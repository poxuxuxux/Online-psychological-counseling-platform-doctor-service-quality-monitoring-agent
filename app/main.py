# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.bootstrap import build_container
from app.config import Settings


def create_app(settings=None, repository=None, model=None, catalog=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.container = await build_container(settings, repository, model, catalog)
        yield

    app = FastAPI(title="Doctor Service Quality Agent Teams", version="2.0.0", lifespan=lifespan)
    origins = settings.frontend_origins if settings else Settings.frontend_origins_from_env()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "X-Demo-Review-Key"],
        )
    app.include_router(router)
    web = Path(__file__).parent / "web"
    if (web / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(web / "index.html")

    return app


app = create_app()
