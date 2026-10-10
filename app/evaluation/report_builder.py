"""功能：把 Agent 结果、核验问题和仲裁状态组织成统一报告对象。"""

from app.domain.models import AgentResult, EvaluationReport


class ReportBuilder:
    """集中构造对外报告；不在报告层重新推断分数或覆盖 Agent 证据。"""

    def build(
        self,
        evaluation_id: str,
        session_id: str,
        results: list[AgentResult],
        verification_issues: list[str] | None = None,
    ) -> EvaluationReport:
        """根据执行状态形成报告，并显式暴露尚未解决的证据问题。"""
        completed = [result for result in results if result.status == "completed"]
        status = "completed" if len(completed) == len(results) else "partial"
        if not results or all(result.status == "failed" for result in results):
            status = "failed"
        return EvaluationReport(
            evaluation_id=evaluation_id,
            session_id=session_id,
            status=status,
            agent_results=results,
            summary="Evaluation output requires evidence review before operational use.",
            limitations=verification_issues or [],
        )
