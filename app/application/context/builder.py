"""功能：为一次 Agent 调用构建最小必要上下文，未通过预检的会话拒绝进入评价。"""

from app.domain.models import (
    AgentInput,
    HistoryContext,
    PreprocessedSession,
    RiskTrigger,
    RunConfig,
)


class ContextBuilder:
    """按授权组装 Agent 输入；知识检索和患者记忆由后续策略逐步接入。"""

    def build(
        self,
        preprocessed: PreprocessedSession,
        selected_skill_ids: list[str] | None = None,
        history_context: HistoryContext | None = None,
        risk_candidates: list[RiskTrigger] | None = None,
        run_config: RunConfig | None = None,
    ) -> AgentInput:
        """创建隔离的 AgentInput；不可评价会话显式拒绝而不是降级评分。"""
        report = preprocessed.report
        if report.verdict == "not_evaluable":
            raise ValueError(
                f"Session {preprocessed.session.session_id} is not evaluable: {report.notes}"
            )
        return AgentInput(
            session=preprocessed.session,
            history_context=history_context,
            selected_skill_ids=selected_skill_ids or [],
            knowledge_context=[],
            memory_context=[],
            risk_candidates=list(risk_candidates or []),
            run_config=run_config or RunConfig(),
        )
