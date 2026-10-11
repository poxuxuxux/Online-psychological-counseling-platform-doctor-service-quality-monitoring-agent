"""功能：验证共享通信池账本、协调器事件写入与管理 Agent 占位的行为。"""

import pytest

from app.agents.registry import AgentRegistry
from app.agents.subagents.manager import ManagerContext, UnconfiguredManagerAgent
from app.application.orchestration.coordinator import EvaluationCoordinator
from app.domain.ledger import AgentMessage, EvaluationEvent, TaskAssignment
from app.domain.models import AgentInput, AgentResult, Finding
from app.infrastructure.repositories.ledger import InMemorySharedLedger
from tests.factories import make_session


class StubAgent:
    """可配置行为的测试 Agent。"""

    def __init__(self, agent_id: str, error: Exception | None = None) -> None:
        self.agent_id = agent_id
        self._error = error

    async def evaluate(self, agent_input: AgentInput) -> AgentResult:
        if self._error:
            raise self._error
        return AgentResult(
            agent_id=self.agent_id,
            status="completed",
            findings=[Finding(metric_id="d4_emotion_recognition", rationale="ok")],
        )


async def test_ledger_is_append_only_and_run_isolated():
    ledger = InMemorySharedLedger()
    await ledger.append_event(
        EvaluationEvent(event_id="e1", run_id="r1", event_type="agent.started", source="coordinator")
    )
    await ledger.append_event(
        EvaluationEvent(event_id="e2", run_id="r2", event_type="agent.completed", source="coordinator")
    )
    assert [event.event_id for event in await ledger.events("r1")] == ["e1"]
    assert [event.event_id for event in await ledger.events("r2")] == ["e2"]
    assert await ledger.events("r3") == []


async def test_task_status_update_and_unknown_task_rejected():
    ledger = InMemorySharedLedger()
    await ledger.append_task(
        TaskAssignment(
            task_id="t1",
            run_id="r1",
            agent_id="empathy",
            evaluation_id="e1",
            session_id="s1",
            context_ref="agent_input:s1",
        )
    )
    await ledger.update_task_status("r1", "t1", "completed")
    assert (await ledger.tasks("r1"))[0].status == "completed"
    with pytest.raises(KeyError):
        await ledger.update_task_status("r1", "ghost", "failed")


async def test_messages_are_isolated_by_run():
    ledger = InMemorySharedLedger()
    await ledger.append_message(
        AgentMessage(message_id="m1", run_id="r1", agent_id="empathy", kind="finding", result_ref="result:m1")
    )
    assert len(await ledger.messages("r1")) == 1
    assert await ledger.messages("r2") == []


async def test_coordinator_publishes_task_and_records_lifecycle_events():
    ledger = InMemorySharedLedger()
    registry = AgentRegistry()
    registry.register(StubAgent("empathy"))
    coordinator = EvaluationCoordinator(registry, ledger=ledger)
    results = await coordinator.run(
        ["empathy"], AgentInput(session=make_session()), run_id="r1", evaluation_id="e1"
    )
    assert results[0].status == "completed"
    assert [event.event_type for event in await ledger.events("r1")] == [
        "task.published",
        "agent.started",
        "agent.completed",
    ]
    tasks = await ledger.tasks("r1")
    assert tasks[0].status == "completed"
    assert tasks[0].agent_id == "empathy"


async def test_coordinator_records_failure_events():
    ledger = InMemorySharedLedger()
    registry = AgentRegistry()
    registry.register(StubAgent("empathy", error=RuntimeError("model down")))
    coordinator = EvaluationCoordinator(registry, ledger=ledger)
    results = await coordinator.run(
        ["empathy"], AgentInput(session=make_session()), run_id="r1", evaluation_id="e1"
    )
    assert results[0].status == "failed"
    assert [event.event_type for event in await ledger.events("r1")] == [
        "task.published",
        "agent.started",
        "agent.failed",
    ]
    assert (await ledger.tasks("r1"))[0].status == "failed"


async def test_coordinator_without_ledger_still_runs():
    registry = AgentRegistry()
    registry.register(StubAgent("empathy"))
    coordinator = EvaluationCoordinator(registry)
    results = await coordinator.run(["empathy"], AgentInput(session=make_session()))
    assert results[0].status == "completed"


async def test_manager_agent_placeholder_raises():
    with pytest.raises(NotImplementedError):
        await UnconfiguredManagerAgent().plan(ManagerContext(session=make_session()))
