"""功能：预留统一 LLM Agent Loop；后续集中实现提示拼装、工具轮次和调用限制。"""

from app.domain.models import AgentInput, AgentResult


class AgentRunner:
    """承载 Agent 的共享运行时策略，避免每个 Agent 各自复制模型循环。"""

    async def run(self, agent_input: AgentInput) -> AgentResult:
        """占位接口；未接入模型 Provider 前拒绝生成看似真实的评分。"""
        raise NotImplementedError("Configure an LLM provider and Agent prompt before running")
