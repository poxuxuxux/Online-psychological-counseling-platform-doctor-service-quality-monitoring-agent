"""功能：聚合 v1 子路由，避免在应用入口堆积具体业务接口。"""

from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
