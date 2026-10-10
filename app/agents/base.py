"""功能：约定不同职责 Agent 的统一异步接口，供协调器并发调用。"""

from typing import Protocol

from app.domain.models import AgentInput, AgentResult


class EvaluationAgent(Protocol):
    """Agent 需声明稳定 ID 并返回统一结果；具体提示词和模型封装独立实现。"""

    @property
    def agent_id(self) -> str:
        """返回路由和审计使用的 Agent 唯一标识。"""
        ...

    async def evaluate(self, agent_input: AgentInput) -> AgentResult:
        """执行当前 Agent 的评价任务；真实实现必须受限于授权 Skill 和工具。"""
        ...
