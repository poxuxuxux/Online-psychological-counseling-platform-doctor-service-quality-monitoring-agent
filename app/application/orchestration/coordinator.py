"""功能：并行调用已注册的评价 Agent，并汇总其结构化结果或失败状态。"""

import asyncio

from app.agents.registry import AgentRegistry
from app.domain.models import AgentInput, AgentResult


class EvaluationCoordinator:
    """协调一次多 Agent 评价；未知 Agent 不会被隐式导入或执行。"""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run(self, agent_ids: list[str], agent_input: AgentInput) -> list[AgentResult]:
        """并发运行路由指定的 Agent；单个 Agent 异常会转成 failed 结果。"""
        agents = [self._registry.get(agent_id) for agent_id in agent_ids]
        outcomes = await asyncio.gather(
            *(agent.evaluate(agent_input) for agent in agents),
            return_exceptions=True,
        )
        results: list[AgentResult] = []
        for agent, outcome in zip(agents, outcomes, strict=True):
            if isinstance(outcome, Exception):
                results.append(
                    AgentResult(agent_id=agent.agent_id, status="failed", error=str(outcome))
                )
            else:
                results.append(outcome)
        return results
