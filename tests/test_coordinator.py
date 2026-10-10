"""功能：验证评价协调器的失败隔离、超时和未知 Agent 处理。"""

import asyncio

from app.agents.registry import AgentRegistry
from app.application.orchestration.coordinator import EvaluationBudget, EvaluationCoordinator
from app.domain.models import AgentInput, AgentResult, Finding
from tests.factories import make_session


class StubAgent:
    """可配置行为的测试 Agent。"""

    def __init__(self, agent_id: str, result=None, error=None, delay: float = 0.0) -> None:
        self.agent_id = agent_id
        self._result = result
        self._error = error
        self._delay = delay

    async def evaluate(self, agent_input: AgentInput) -> AgentResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._result or AgentResult(
            agent_id=self.agent_id,
            status="completed",
            findings=[Finding(metric_id="D4", rationale="ok")],
        )


def make_agent_input() -> AgentInput:
    return AgentInput(session=make_session())


async def test_agent_exception_becomes_failed_result():
    registry = AgentRegistry()
    registry.register(StubAgent("professional", error=RuntimeError("model down")))
    coordinator = EvaluationCoordinator(registry)
    results = await coordinator.run(["professional"], make_agent_input())
    assert results[0].status == "failed"
    assert "model down" in results[0].error


async def test_unknown_agent_id_becomes_failed_result():
    coordinator = EvaluationCoordinator(AgentRegistry())
    results = await coordinator.run(["ghost"], make_agent_input())
    assert results[0].status == "failed"
    assert "not registered" in results[0].error


async def test_slow_agent_times_out():
    registry = AgentRegistry()
    registry.register(StubAgent("empathy", delay=0.5))
    coordinator = EvaluationCoordinator(
        registry, budget=EvaluationBudget(agent_timeout_seconds=0.05, max_concurrency=2)
    )
    results = await coordinator.run(["empathy"], make_agent_input())
    assert results[0].status == "failed"
    assert results[0].error == "timed_out"


async def test_single_failure_does_not_block_others():
    registry = AgentRegistry()
    registry.register(StubAgent("professional", error=RuntimeError("boom")))
    registry.register(StubAgent("empathy"))
    coordinator = EvaluationCoordinator(registry)
    results = await coordinator.run(["professional", "empathy"], make_agent_input())
    by_id = {result.agent_id: result for result in results}
    assert by_id["professional"].status == "failed"
    assert by_id["empathy"].status == "completed"
