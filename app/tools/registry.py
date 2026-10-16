"""功能：集中登记 ToolSpec 与 Handler；此注册表不提供任意代码执行能力。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    """工具描述和 Agent 白名单；输入参数 schema 后续接入统一校验器。"""

    name: str
    description: str
    allowed_agents: frozenset[str]
    request_model: type[BaseModel] | None = None
    timeout_seconds: float = 10.0
    version: str = "1.0.0"


class ToolRegistry:
    """保存工具规格与处理器的映射，供 Dispatcher 校验后调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolHandler]] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        """注册一个工具；同名冲突必须修正，不能静默覆盖旧 Handler。"""
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = (spec, handler)

    def get(self, name: str) -> tuple[ToolSpec, ToolHandler]:
        """返回已注册工具及其 Handler；未知工具明确失败。"""
        try:
            return self._tools[name]
        except KeyError as error:
            raise KeyError(f"Tool is not registered: {name}") from error
