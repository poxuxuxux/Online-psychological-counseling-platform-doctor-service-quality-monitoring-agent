# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.bootstrap import build_container


def create_app(settings=None, repository=None, model=None, catalog=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.container = await build_container(settings, repository, model, catalog)
        yield

    app = FastAPI(title="Doctor Service Quality Agent Teams", version="2.0.0", lifespan=lifespan)
    app.include_router(router)
    web = Path(__file__).parent / "web"
    if (web / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(web / "index.html")

    return app


app = create_app()
