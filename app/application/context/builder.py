"""功能：为一次 Agent 调用构建最小必要上下文，防止无关或未授权数据泄漏。"""

from app.domain.models import AgentInput, ConversationSession


class ContextBuilder:
    """按授权组装 Agent 输入；当前实现仅携带本次会话和显式选择的 Skill。"""

    def build(
        self,
        session: ConversationSession,
        selected_skill_ids: list[str] | None = None,
    ) -> AgentInput:
        """创建隔离的 AgentInput；知识检索和患者记忆由后续策略逐步接入。"""
        return AgentInput(
            session=session,
            selected_skill_ids=selected_skill_ids or [],
            knowledge_context=[],
            memory_context=[],
        )
