"""功能：验证评价用例端到端骨架：预处理不可评价、无 Agent 注册和正常失败隔离。"""

from app.agents.registry import AgentRegistry
from app.application.context.builder import ContextBuilder
from app.application.orchestration.coordinator import EvaluationCoordinator
from app.application.orchestration.router import PolicyRouter
from app.application.preprocessing.pipeline import PreprocessingPipeline
from app.application.preprocessing.stages import (
    DesensitizationStage,
    NormalizationStage,
    PreflightStage,
    TranscriptionStage,
)
from app.application.use_cases.evaluate_session import EvaluateSessionUseCase
from app.evaluation.evidence_verifier import EvidenceVerifier
from app.evaluation.report_builder import ReportBuilder
from app.infrastructure.media.transcriber import UnconfiguredTranscriber
from app.infrastructure.security.redactor import (
    InMemoryRedactionMapRepository,
    SyntheticDemoRedactor,
)
from tests.factories import make_message, make_session


def build_use_case(agent_registry=None) -> EvaluateSessionUseCase:
    """装配与 bootstrap 等价的垂直切片。"""
    agent_registry = agent_registry or AgentRegistry()
    pipeline = PreprocessingPipeline(
        stages=(
            NormalizationStage(),
            TranscriptionStage(UnconfiguredTranscriber()),
            DesensitizationStage(SyntheticDemoRedactor(), InMemoryRedactionMapRepository()),
            PreflightStage(),
        )
    )
    return EvaluateSessionUseCase(
        pipeline=pipeline,
        router=PolicyRouter(),
        context_builder=ContextBuilder(),
        coordinator=EvaluationCoordinator(agent_registry),
        evidence_verifier=EvidenceVerifier(),
        report_builder=ReportBuilder(),
    )


async def test_not_evaluable_session_returns_failed_report_with_notes():
    use_case = build_use_case()
    session = make_session(messages=[make_message("m-001", role="patient", content="有人吗？")])
    report = await use_case.execute(session)
    assert report.status == "failed"
    assert any("no_doctor_messages" in note for note in report.limitations)


async def test_unregistered_agents_yield_partial_report_with_errors():
    use_case = build_use_case()
    report = await use_case.execute(make_session())
    assert report.status == "failed"  # 三个路由 Agent 均未注册
    assert len(report.agent_results) == 3
    assert all(result.status == "failed" for result in report.agent_results)
    assert all("not registered" in result.error for result in report.agent_results)


async def test_evaluable_session_with_agent_failure_keeps_report_traceable():
    report = await build_use_case().execute(make_session())
    assert report.summary  # 报告始终携带复核提示
    assert report.evaluation_id.startswith("eval-")
