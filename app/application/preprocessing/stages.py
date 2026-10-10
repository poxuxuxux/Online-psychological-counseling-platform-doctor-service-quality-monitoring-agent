"""功能：实现规范化、转写、脱敏和预检四个标准预处理阶段。"""

from dataclasses import dataclass
from typing import Literal

from app.application.preprocessing.ports import (
    ContentRedactor,
    RedactionMapRepository,
    RedactionRecord,
    Transcriber,
)
from app.domain.models import (
    ConversationSession,
    Message,
    RedactionSummary,
    TranscriptSummary,
)

StageStatus = Literal["completed", "partial", "failed", "skipped"]


@dataclass(frozen=True)
class StageOutcome:
    """单阶段处理结果；failed 会阻断后续阶段，以保护数据安全。"""

    session: ConversationSession
    status: StageStatus
    issues: tuple[str, ...] = ()
    redaction: RedactionSummary | None = None
    transcripts: tuple[TranscriptSummary, ...] = ()


class PreprocessingStage:
    """所有预处理阶段实现此协议；阶段顺序由管道装配决定。"""

    stage_name: str
    stage_version: str

    async def process(self, session: ConversationSession) -> StageOutcome:  # pragma: no cover - 协议提示
        """处理会话并返回新会话与阶段状态。"""
        raise NotImplementedError


class NormalizationStage(PreprocessingStage):
    """确定性文本规范化：折叠空白、统一格式；不做改变语义的改写。"""

    stage_name = "normalization"
    stage_version = "1.0.0"

    async def process(self, session: ConversationSession) -> StageOutcome:
        """规范化非空消息文本；空内容留给预检阶段统一判定。"""
        messages = [
            message.model_copy(update={"content": " ".join(message.content.split())})
            if message.content
            else message
            for message in session.messages
        ]
        return StageOutcome(
            session=session.model_copy(update={"messages": messages}),
            status="completed",
        )


class TranscriptionStage(PreprocessingStage):
    """将音视频消息转写为可评价文本；原始媒体不进入 Agent，只注入派生文本。"""

    stage_name = "transcription"
    stage_version = "1.0.0"

    def __init__(self, transcriber: Transcriber, min_confidence: float = 0.6) -> None:
        self._transcriber = transcriber
        self._min_confidence = min_confidence

    async def process(self, session: ConversationSession) -> StageOutcome:
        """逐条转写音视频消息；单条失败降级为 partial，不阻断其他消息。"""
        summaries: list[TranscriptSummary] = []
        issues: list[str] = []
        messages: list[Message] = []
        for message in session.messages:
            if message.modality == "text" or message.media is None or message.transcript is not None:
                messages.append(message)
                continue
            try:
                transcript = await self._transcriber.transcribe(message.media)
            except Exception as error:  # noqa: BLE001 - 单条转写失败不放大成整段管道失败
                issues.append(f"{message.message_id}: transcription_failed: {error}")
                messages.append(message)
                continue
            content = "\n".join(segment.text for segment in transcript.segments)
            confidences = [s.confidence for s in transcript.segments if s.confidence is not None]
            low_count = sum(
                1
                for s in transcript.segments
                if s.confidence is not None and s.confidence < self._min_confidence
            )
            if low_count:
                issues.append(f"{message.message_id}: low_confidence_segments:{low_count}")
            messages.append(
                message.model_copy(update={"content": content, "transcript": transcript})
            )
            summaries.append(
                TranscriptSummary(
                    message_id=message.message_id,
                    engine=transcript.engine,
                    engine_version=transcript.engine_version,
                    segment_count=len(transcript.segments),
                    average_confidence=(
                        sum(confidences) / len(confidences) if confidences else None
                    ),
                )
            )
        return StageOutcome(
            session=session.model_copy(update={"messages": messages}),
            status="partial" if issues else "completed",
            issues=tuple(issues),
            transcripts=tuple(summaries),
        )


class DesensitizationStage(PreprocessingStage):
    """对全部可评价文本执行脱敏；任何失败都按 failed 阻断，防止未脱敏数据外流。"""

    stage_name = "desensitization"
    stage_version = "1.0.0"

    def __init__(self, redactor: ContentRedactor, map_repository: RedactionMapRepository) -> None:
        self._redactor = redactor
        self._map_repository = map_repository

    async def process(self, session: ConversationSession) -> StageOutcome:
        """脱敏每条消息并立即把映射写入隔离库；映射不随会话流转。"""
        records: list[RedactionRecord] = []
        messages: list[Message] = []
        try:
            for message in session.messages:
                result = self._redactor.redact(message.message_id, message.content)
                records.extend(result.records)
                messages.append(
                    message.model_copy(
                        update={"content": result.redacted_text, "redaction_applied": True}
                    )
                )
        except NotImplementedError as error:
            return StageOutcome(session=session, status="failed", issues=(f"redactor_unconfigured: {error}",))
        except Exception as error:  # noqa: BLE001 - 脱敏失败必须阻断，防止未脱敏数据外流
            return StageOutcome(session=session, status="failed", issues=(f"redaction_failed: {error}",))
        await self._map_repository.save(session.session_id, records)
        summary = RedactionSummary(
            ruleset_version=self._redactor.ruleset_version,
            masked_item_count=len(records),
            categories=sorted({record.rule_id for record in records}),
        )
        return StageOutcome(
            session=session.model_copy(update={"messages": messages}),
            status="completed",
            redaction=summary,
        )


class PreflightStage(PreprocessingStage):
    """评价前预检：发言方覆盖、空内容、缺失时间戳等会话完整性问题。"""

    stage_name = "preflight"
    stage_version = "1.0.0"

    def __init__(self, max_unknown_role_ratio: float = 0.5) -> None:
        self._max_unknown_role_ratio = max_unknown_role_ratio

    async def process(self, session: ConversationSession) -> StageOutcome:
        """产出可审阅的预检问题；问题映射到评价限制而不是直接丢掉会话。"""
        issues: list[str] = []
        if not session.messages:
            issues.append("empty_session")
        else:
            roles = [message.role for message in session.messages]
            if "doctor" not in roles:
                issues.append("no_doctor_messages")
            unknown_ratio = roles.count("unknown") / len(roles)
            if unknown_ratio > self._max_unknown_role_ratio:
                issues.append(f"unknown_role_ratio_exceeded:{unknown_ratio:.2f}")
            empty_count = sum(1 for message in session.messages if not message.content.strip())
            if empty_count:
                issues.append(f"empty_content_messages:{empty_count}")
            if any(message.timestamp is None for message in session.messages):
                issues.append("missing_timestamps:affects_d2_responsiveness")
        return StageOutcome(
            session=session,
            status="partial" if issues else "completed",
            issues=tuple(issues),
        )
