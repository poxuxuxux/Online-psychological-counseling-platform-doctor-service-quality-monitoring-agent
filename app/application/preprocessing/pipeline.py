"""功能：按固定顺序执行预处理阶段，产出带报告的规范化会话。"""

from collections.abc import Sequence
from typing import Literal

from app.application.preprocessing.stages import PreprocessingStage, StageOutcome
from app.domain.models import (
    ConversationSession,
    PreprocessedSession,
    PreprocessingReport,
    PreprocessingStageReport,
)


class PreprocessingPipeline:
    """确定性编排预处理阶段；阶段顺序由装配决定，LLM 不参与预处理决策。"""

    def __init__(self, stages: Sequence[PreprocessingStage]) -> None:
        self._stages = tuple(stages)

    async def run(self, session: ConversationSession) -> PreprocessedSession:
        """顺序执行各阶段；单阶段崩溃被隔离成 failed，后续阶段标记 skipped。"""
        reports: list[PreprocessingStageReport] = []
        redaction = None
        transcripts: list = []
        notes: list[str] = []
        current = session
        blocked = False

        for stage in self._stages:
            if blocked:
                reports.append(
                    PreprocessingStageReport(
                        stage_name=stage.stage_name,
                        stage_version=stage.stage_version,
                        status="skipped",
                    )
                )
                continue
            try:
                outcome: StageOutcome = await stage.process(current)
            except Exception as error:  # noqa: BLE001 - 阶段异常必须被隔离，避免半处理数据继续流转
                outcome = StageOutcome(
                    session=current,
                    status="failed",
                    issues=(f"stage_crashed:{type(error).__name__}:{error}",),
                )
            current = outcome.session
            reports.append(
                PreprocessingStageReport(
                    stage_name=stage.stage_name,
                    stage_version=stage.stage_version,
                    status=outcome.status,
                    issues=list(outcome.issues),
                )
            )
            notes.extend(f"{stage.stage_name}:{issue}" for issue in outcome.issues)
            if outcome.redaction is not None:
                redaction = outcome.redaction
            transcripts.extend(outcome.transcripts)
            if outcome.status == "failed":
                blocked = True

        if blocked:
            status: Literal["completed", "partial", "failed"] = "failed"
        elif notes:
            status = "partial"
        else:
            status = "completed"
        return PreprocessedSession(
            session=current,
            report=PreprocessingReport(
                session_id=session.session_id,
                status=status,
                verdict=self._verdict(reports, current),
                stage_reports=reports,
                redaction=redaction,
                transcripts=transcripts,
                notes=notes,
            ),
        )

    @staticmethod
    def _verdict(
        reports: Sequence[PreprocessingStageReport],
        session: ConversationSession,
    ) -> str:
        """确定性判定可评价性：安全阶段失败或缺医生发言则不可评价。"""
        if any(report.status == "failed" for report in reports):
            return "not_evaluable"
        if not session.messages or all(message.role != "doctor" for message in session.messages):
            return "not_evaluable"
        if any(report.status == "partial" for report in reports):
            return "partially_evaluable"
        return "evaluable"
