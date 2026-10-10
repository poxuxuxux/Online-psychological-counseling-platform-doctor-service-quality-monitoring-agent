"""功能：显式注册 Agent 实例，供路由器和协调器安全查找。"""

from app.agents.base import EvaluationAgent


class AgentRegistry:
    """基于白名单管理 Agent；重复 ID 和未注册 ID 都明确报错。"""

    def __init__(self) -> None:
        self._agents: dict[str, EvaluationAgent] = {}

    def register(self, agent: EvaluationAgent) -> None:
        """注册 Agent；重复标识视为装配错误而不是静默覆盖。"""
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> EvaluationAgent:
        """按稳定 ID 获取已注册 Agent；未知 ID 不触发动态导入。"""
        try:
            return self._agents[agent_id]
        except KeyError as error:
            raise KeyError(f"Agent is not registered: {agent_id}") from error
