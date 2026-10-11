"""功能：单会话评价垂直编排：预处理 → 路由 → 上下文 → 并发评价 → 证据核验 → 报告。"""

import uuid

from app.application.context.builder import ContextBuilder
from app.application.orchestration.coordinator import EvaluationCoordinator
from app.application.orchestration.router import PolicyRouter
from app.application.preprocessing.pipeline import PreprocessingPipeline
from app.domain.models import ConversationSession, EvaluationReport
from app.evaluation.evidence_verifier import EvidenceVerifier
from app.evaluation.report_builder import ReportBuilder


class EvaluateSessionUseCase:
    """封装单次会话评价的应用流程，避免将业务编排写进 FastAPI 路由。"""

    def __init__(
        self,
        pipeline: PreprocessingPipeline,
        router: PolicyRouter,
        context_builder: ContextBuilder,
        coordinator: EvaluationCoordinator,
        evidence_verifier: EvidenceVerifier,
        report_builder: ReportBuilder,
    ) -> None:
        self._pipeline = pipeline
        self._router = router
        self._context_builder = context_builder
        self._coordinator = coordinator
        self._evidence_verifier = evidence_verifier
        self._report_builder = report_builder

    async def execute(self, session: ConversationSession) -> EvaluationReport:
        """执行完整评价；任一环节不满足条件都保留状态和原因，不伪造结果。"""
        evaluation_id = f"eval-{uuid.uuid4()}"
        run_id = f"run-{uuid.uuid4()}"

        preprocessed = await self._pipeline.run(session)
        if preprocessed.report.verdict == "not_evaluable":
            return self._report_builder.build(
                evaluation_id,
                session.session_id,
                results=[],
                verification_issues=preprocessed.report.notes,
            )

        plan = self._router.route(preprocessed.session)
        if not plan.agent_ids:
            return self._report_builder.build(
                evaluation_id,
                session.session_id,
                results=[],
                verification_issues=[f"routing_skipped:{reason}" for reason in plan.reasons],
            )

        try:
            agent_input = self._context_builder.build(preprocessed)
        except ValueError as error:
            return self._report_builder.build(
                evaluation_id,
                session.session_id,
                results=[],
                verification_issues=[str(error)],
            )

        results = await self._coordinator.run(
            list(plan.agent_ids), agent_input, run_id=run_id, evaluation_id=evaluation_id
        )
        verification_issues: list[str] = []
        for result in results:
            verification_issues.extend(self._evidence_verifier.verify(result, preprocessed.session))
        return self._report_builder.build(
            evaluation_id,
            session.session_id,
            results,
            verification_issues=verification_issues,
            preprocessing_notes=preprocessed.report.notes,
        )
