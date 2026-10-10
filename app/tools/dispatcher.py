"""功能：执行工具调用前检查工具注册和 Agent 白名单，然后分发给 Handler。"""

from typing import Any

from app.tools.registry import ToolRegistry


class ToolDispatcher:
    """集中执行工具策略；生产环境还需加入参数 schema、超时和审计钩子。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def dispatch(
        self,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """仅允许白名单 Agent 调用已注册工具，不开放 shell 或任意文件操作。"""
        spec, handler = self._registry.get(tool_name)
        if agent_id not in spec.allowed_agents:
            raise PermissionError(f"Agent {agent_id} cannot call tool {tool_name}")
        return await handler(arguments)
