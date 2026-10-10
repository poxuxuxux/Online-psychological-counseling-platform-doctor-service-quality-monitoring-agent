"""功能：提供轻量健康检查，用于本地启动确认和部署存活探测。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """返回服务存活状态；此接口不检查数据库或模型等下游依赖。"""
    return {"status": "ok"}
