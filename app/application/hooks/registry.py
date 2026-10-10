"""功能：注册并触发应用事件回调；安全权限仍由确定性策略单独负责。"""

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

    async def emit(self, event_name: str, payload: dict[str, Any]) -> None:
        """依次触发事件回调；生产实现需定义超时、错误隔离和审计规则。"""
        for hook in self._hooks[event_name]:
            await hook(payload)
