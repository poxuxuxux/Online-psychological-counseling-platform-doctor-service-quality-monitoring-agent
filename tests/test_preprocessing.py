"""功能：验证预处理管道的阶段编排、可评价性判定和安全阻断。"""

from app.application.preprocessing.pipeline import PreprocessingPipeline
from app.application.preprocessing.stages import (
    DesensitizationStage,
    NormalizationStage,
    PreflightStage,
    StageOutcome,
    TranscriptionStage,
)
from app.infrastructure.media.transcriber import UnconfiguredTranscriber
from app.infrastructure.security.redactor import (
    InMemoryRedactionMapRepository,
    RuleBasedContentRedactor,
    SyntheticDemoRedactor,
)
from tests.factories import make_message, make_session


def build_default_pipeline(redactor=None) -> PreprocessingPipeline:
    """装配与 bootstrap 相同顺序的标准阶段。"""
    return PreprocessingPipeline(
        stages=(
            NormalizationStage(),
            TranscriptionStage(UnconfiguredTranscriber()),
            DesensitizationStage(
                redactor or SyntheticDemoRedactor(),
                InMemoryRedactionMapRepository(),
            ),
            PreflightStage(),
        )
    )


async def test_pure_text_session_is_evaluable():
    pipeline = build_default_pipeline()
    result = await pipeline.run(make_session())
    assert result.report.verdict == "evaluable"
    assert result.report.status == "completed"
    assert result.session.messages[0].redaction_applied is True


async def test_content_is_whitespace_normalized():
    pipeline = build_default_pipeline()
    session = make_session(
        messages=[make_message("m-001", role="doctor", content="  你好   世界  \n")]
    )
    result = await pipeline.run(session)
    assert result.session.messages[0].content == "你好 世界"


async def test_session_without_doctor_messages_is_not_evaluable():
    pipeline = build_default_pipeline()
    session = make_session(
        messages=[make_message("m-001", role="patient", content="有人吗？")]
    )
    result = await pipeline.run(session)
    assert result.report.verdict == "not_evaluable"
    assert "preflight:no_doctor_messages" in result.report.notes


async def test_redaction_failure_blocks_pipeline_and_skips_preflight():
    pipeline = build_default_pipeline(redactor=RuleBasedContentRedactor())
    result = await pipeline.run(make_session())
    assert result.report.verdict == "not_evaluable"
    statuses = {report.stage_name: report.status for report in result.report.stage_reports}
    assert statuses["desensitization"] == "failed"
    assert statuses["preflight"] == "skipped"
    assert any("redactor_unconfigured" in note for note in result.report.notes)


async def test_stage_crash_is_isolated():
    class CrashingStage:
        stage_name = "crash"
        stage_version = "0.0.0"

        async def process(self, session):
            raise RuntimeError("boom")

    pipeline = PreprocessingPipeline(stages=(CrashingStage(), PreflightStage()))
    result = await pipeline.run(make_session())
    assert result.report.verdict == "not_evaluable"
    assert any("stage_crashed" in note for note in result.report.notes)


async def test_missing_timestamps_flag_d2_limitation():
    pipeline = build_default_pipeline()
    session = make_session(
        messages=[
            make_message("m-001", role="patient", content="我最近总是睡不好。", omit_timestamp=True),
            make_message("m-002", role="doctor", content="听起来困扰你一段时间了。", omit_timestamp=True),
        ]
    )
    result = await pipeline.run(session)
    assert result.report.verdict == "partially_evaluable"  # 无时间戳只降级为限制
    assert "preflight:missing_timestamps:affects_d2_responsiveness" in result.report.notes
    assert result.report.status == "partial"


def test_outcome_dataclass_carries_session():
    outcome = StageOutcome(session=make_session(), status="completed")
    assert outcome.session.session_id == "s-001"
