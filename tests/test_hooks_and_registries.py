"""功能：验证 Hook 回调错误隔离与各注册表的失败语义。"""

import pytest

from app.agents.registry import AgentRegistry
from app.application.hooks.registry import HookRegistry
from app.infrastructure.importers.registry import ImporterRegistry
from app.tools.registry import ToolRegistry


async def test_hook_error_does_not_block_other_hooks():
    registry = HookRegistry()
    calls: list[str] = []

    async def broken(payload):
        raise RuntimeError("hook crashed")

    async def healthy(payload):
        calls.append("healthy")

    registry.register("session.imported", broken)
    registry.register("session.imported", healthy)
    errors = await registry.emit("session.imported", {})
    assert calls == ["healthy"]
    assert len(errors) == 1
    assert "hook crashed" in errors[0]


class MinimalAgent:
    agent_id = "empathy"

    async def evaluate(self, agent_input):
        raise NotImplementedError


def test_agent_registry_rejects_duplicates():
    registry = AgentRegistry()
    registry.register(MinimalAgent())
    with pytest.raises(ValueError):
        registry.register(MinimalAgent())


def test_agent_registry_rejects_unknown_id():
    with pytest.raises(KeyError):
        AgentRegistry().get("ghost")


def test_importer_registry_rejects_duplicate_and_unknown():
    registry = ImporterRegistry()
    registry.register("json", object())
    with pytest.raises(ValueError):
        registry.register("json", object())
    with pytest.raises(KeyError):
        registry.get("csv")


def test_tool_registry_rejects_duplicates():
    from app.tools.registry import ToolSpec

    registry = ToolRegistry()

    async def handler(arguments):
        return None

    spec = ToolSpec(name="load_skill", description="加载技能", allowed_agents=frozenset({"empathy"}))
    registry.register(spec, handler)
    with pytest.raises(ValueError):
        registry.register(spec, handler)
