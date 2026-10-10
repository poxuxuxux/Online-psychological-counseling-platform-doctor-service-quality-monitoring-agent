"""功能：注册并触发应用事件回调；单个回调故障被隔离，不阻断事件流。"""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Hook = Callable[[dict[str, Any]], Awaitable[None]]


class HookRegistry:
    """保存按事件名注册的异步回调，供 Agent、工具和评价流程复用。"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Hook]] = defaultdict(list)

    def register(self, event_name: str, hook: Hook) -> None:
        """将回调加入事件列表；同一事件允许多个模块独立订阅。"""
        self._hooks[event_name].append(hook)

    async def emit(self, event_name: str, payload: dict[str, Any]) -> list[str]:
        """依次触发回调并返回错误摘要；单个回调异常不影响其他回调。"""
        errors: list[str] = []
        for hook in list(self._hooks[event_name]):
            try:
                await hook(payload)
            except Exception as error:  # noqa: BLE001 - 隔离回调故障，保持风险 Hook 链路可用
                errors.append(f"{event_name}:{type(error).__name__}:{error}")
        return errors
