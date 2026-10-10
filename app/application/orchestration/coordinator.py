"""功能：并发调用已注册的评价 Agent，施加超时与并发预算并汇总结果。"""

import asyncio
from dataclasses import dataclass

from app.agents.registry import AgentRegistry
from app.domain.models import AgentInput, AgentResult


@dataclass(frozen=True)
class EvaluationBudget:
    """单次评价的资源预算；超时和并发上限来自配置，不硬编码在流程里。"""

    agent_timeout_seconds: float = 120.0
    max_concurrency: int = 3


class EvaluationCoordinator:
    """协调一次多 Agent 评价；未知 Agent、超时和异常都转为 failed 结果。"""

    def __init__(self, registry: AgentRegistry, budget: EvaluationBudget | None = None) -> None:
        self._registry = registry
        self._budget = budget or EvaluationBudget()

    async def run(self, agent_ids: list[str], agent_input: AgentInput) -> list[AgentResult]:
        """在预算内并发运行 Agent；单个失败不影响其他 Agent 的结果。"""
        semaphore = asyncio.Semaphore(self._budget.max_concurrency)
        outcomes = await asyncio.gather(
            *(self._run_one(agent_id, agent_input, semaphore) for agent_id in agent_ids),
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
    ) -> AgentResult:
        """执行单个 Agent：查找失败、超时和运行异常分别转为 failed。"""
        async with semaphore:
            try:
                agent = self._registry.get(agent_id)
            except KeyError as error:
                return AgentResult(agent_id=agent_id, status="failed", error=str(error))
            try:
                return await asyncio.wait_for(
                    agent.evaluate(agent_input),
                    timeout=self._budget.agent_timeout_seconds,
                )
            except TimeoutError:
                return AgentResult(agent_id=agent_id, status="failed", error="timed_out")
            except Exception as error:  # noqa: BLE001 - 单 Agent 故障必须被隔离成 failed 结果
                return AgentResult(agent_id=agent_id, status="failed", error=str(error))
