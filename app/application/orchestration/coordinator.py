"""功能：并发调用已注册的评价 Agent，施加超时与并发预算，并把任务与阶段事件写入共享通信池。"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.agents.registry import AgentRegistry
from app.domain.ledger import EvaluationEvent, SharedLedger, TaskAssignment
from app.domain.models import AgentInput, AgentResult


@dataclass(frozen=True)
class EvaluationBudget:
    """单次评价的资源预算；超时和并发上限来自配置，不硬编码在流程里。"""

    agent_timeout_seconds: float = 120.0
    max_concurrency: int = 3


class EvaluationCoordinator:
    """协调一次多 Agent 评价；未知 Agent、超时和异常都转为 failed 结果。

    共享通信池是被动账本：仅在任务发布与阶段边界写入记录，Agent 不通过池
    自主触发其他 Agent；未提供 run_id 或账本时不写池，行为与之前一致。
    """

    def __init__(
        self,
        registry: AgentRegistry,
        budget: EvaluationBudget | None = None,
        ledger: SharedLedger | None = None,
    ) -> None:
        self._registry = registry
        self._budget = budget or EvaluationBudget()
        self._ledger = ledger

    async def run(
        self,
        agent_ids: list[str],
        agent_input: AgentInput,
        run_id: str | None = None,
        evaluation_id: str | None = None,
    ) -> list[AgentResult]:
        """在预算内并发运行 Agent；单个失败不影响其他 Agent 的结果。"""
        semaphore = asyncio.Semaphore(self._budget.max_concurrency)
        outcomes = await asyncio.gather(
            *(
                self._run_one(agent_id, agent_input, semaphore, run_id, evaluation_id)
                for agent_id in agent_ids
            ),
            return_exceptions=True,
        )
        results: list[AgentResult] = []
        for agent_id, outcome in zip(agent_ids, outcomes, strict=True):
            if isinstance(outcome, AgentResult):
                results.append(outcome)
            else:
                results.append(
                    AgentResult(agent_id=agent_id, status="failed", error=str(outcome))
                )
        return results

    async def _run_one(
        self,
        agent_id: str,
        agent_input: AgentInput,
        semaphore: asyncio.Semaphore,
        run_id: str | None,
        evaluation_id: str | None,
    ) -> AgentResult:
        """执行单个 Agent：查找失败、超时和运行异常分别转为 failed 并记录事件。"""
        async with semaphore:
            task_id = f"task-{uuid.uuid4()}"
            await self._publish_task(task_id, agent_id, agent_input, run_id, evaluation_id)
            await self._record(run_id, "agent.started", agent_id, evaluation_id)
            try:
                agent = self._registry.get(agent_id)
            except KeyError as error:
                await self._settle_task(task_id, run_id, "failed")
                await self._record(run_id, "agent.failed", agent_id, evaluation_id, str(error))
                return AgentResult(agent_id=agent_id, status="failed", error=str(error))
            try:
                result = await asyncio.wait_for(
                    agent.evaluate(agent_input),
                    timeout=self._budget.agent_timeout_seconds,
                )
            except TimeoutError:
                result = AgentResult(agent_id=agent_id, status="failed", error="timed_out")
            except Exception as error:  # noqa: BLE001 - 单 Agent 故障必须被隔离成 failed 结果
                result = AgentResult(agent_id=agent_id, status="failed", error=str(error))
            if result.status == "failed":
                await self._settle_task(task_id, run_id, "failed")
                await self._record(run_id, "agent.failed", agent_id, evaluation_id, result.error)
            else:
                await self._settle_task(task_id, run_id, "completed")
                await self._record(run_id, "agent.completed", agent_id, evaluation_id)
            return result

    async def _publish_task(
        self,
        task_id: str,
        agent_id: str,
        agent_input: AgentInput,
        run_id: str | None,
        evaluation_id: str | None,
    ) -> None:
        """向池发布任务单；未启用账本时跳过。"""
        if self._ledger is None or not run_id:
            return
        await self._ledger.append_task(
            TaskAssignment(
                task_id=task_id,
                run_id=run_id,
                agent_id=agent_id,
                evaluation_id=evaluation_id or "",
                session_id=agent_input.session.session_id,
                skill_ids=list(agent_input.selected_skill_ids),
                context_ref=f"agent_input:{agent_input.session.session_id}",
            )
        )
        await self._record(run_id, "task.published", "coordinator", evaluation_id)

    async def _settle_task(self, task_id: str, run_id: str | None, status: str) -> None:
        """回写任务单终态；未启用账本时跳过。"""
        if self._ledger is None or not run_id:
            return
        await self._ledger.update_task_status(run_id, task_id, status)  # type: ignore[arg-type]

    async def _record(
        self,
        run_id: str | None,
        event_type: str,
        agent_id: str,
        evaluation_id: str | None,
        error: str | None = None,
    ) -> None:
        """追加阶段事件；payload 只携带对象 ID，不携带会话正文。"""
        if self._ledger is None or not run_id:
            return
        refs = {"agent_id": agent_id, "evaluation_id": evaluation_id or ""}
        if error:
            refs["error"] = error
        await self._ledger.append_event(
            EvaluationEvent(
                event_id=f"event-{uuid.uuid4()}",
                run_id=run_id,
                event_type=event_type,  # type: ignore[arg-type]
                source="coordinator",
                occurred_at=datetime.now(UTC),
                payload_refs=refs,
            )
        )
