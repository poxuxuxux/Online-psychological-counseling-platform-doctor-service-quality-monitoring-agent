"""功能：聚合 v1 子路由，避免在应用入口堆积具体业务接口。"""

from fastapi import APIRouter

from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.health import router as health_router
from app.api.v1.metric_runs import router as metric_runs_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(evaluations_router, tags=["evaluations"])
api_router.include_router(metric_runs_router)
