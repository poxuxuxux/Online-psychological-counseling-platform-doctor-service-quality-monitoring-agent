"""功能：提供轻量健康检查，用于本地启动确认和部署存活探测。"""

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """返回服务存活状态；此接口不检查数据库或模型等下游依赖。"""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(request: Request) -> JSONResponse:
    """检查应用及 PostgreSQL 的真实连接状态。"""
    database = await request.app.state.container.evaluation_store.readiness()
    ready = bool(database["connected"])
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "not_ready", "database": database},
    )
