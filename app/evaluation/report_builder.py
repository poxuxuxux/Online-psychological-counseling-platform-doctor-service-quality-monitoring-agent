"""功能：把 Agent 结果、核验问题和预处理限制组织成统一报告对象。"""

from app.domain.models import AgentResult, EvaluationReport


class ReportBuilder:
    """集中构造对外报告；不在报告层重新推断分数或覆盖 Agent 证据。"""

    def build(
        self,
        evaluation_id: str,
        session_id: str,
        results: list[AgentResult],
        verification_issues: list[str] | None = None,
        preprocessing_notes: list[str] | None = None,
    ) -> EvaluationReport:
        """根据执行状态形成报告，并显式暴露证据与预处理限制。"""
        completed = [result for result in results if result.status == "completed"]
        status = "completed" if completed and len(completed) == len(results) else "partial"
        if not results or all(result.status == "failed" for result in results):
            status = "failed"
        return EvaluationReport(
            evaluation_id=evaluation_id,
            session_id=session_id,
            status=status,
            agent_results=results,
            summary=(
                "演示评价已完成。系统从专业服务、过程响应、共情关系三个职责视角生成了"
                "可定位原文的质检结果；结论仍需人工复核。"
                if completed
                else "当前会话未能完成评价，请根据限制项检查输入和运行配置。"
            ),
            limitations=list(verification_issues or []) + list(preprocessing_notes or []),
        )
