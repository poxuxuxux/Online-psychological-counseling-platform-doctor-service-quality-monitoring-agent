"""功能：定义多模态会话、预处理报告、历史上下文、风险候选、证据和报告等跨模块契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Modality = Literal["text", "audio", "video"]
SpeakerRole = Literal["doctor", "patient", "system", "unknown"]
ConsultationRound = Literal["initial", "follow_up", "unknown"]


class MediaAsset(BaseModel):
    """一段已授权导入的原始音视频资产；只保存受控存储引用，不内嵌二进制。"""

    media_id: str
    modality: Literal["audio", "video"]
    storage_ref: str
    mime_type: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)


class TranscriptSegment(BaseModel):
    """ASR 转写片段；时间偏移用于把报告证据定位回原始音视频位置。"""

    segment_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    speaker_role: SpeakerRole = "unknown"
    confidence: float | None = Field(default=None, ge=0, le=1)


class TranscriptInfo(BaseModel):
    """消息级转写元数据；引擎与版本必须记录，便于复现、回归和证据追溯。"""

    engine: str
    engine_version: str
    language: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)


class Message(BaseModel):
    """规范化单条对话；content 是预处理后的可评价文本（原文或转写并脱敏后）。"""

    message_id: str
    role: SpeakerRole = "unknown"
    modality: Modality = "text"
    content: str
    sequence: int = Field(ge=0)
    timestamp: datetime | None = None
    media: MediaAsset | None = None
    transcript: TranscriptInfo | None = None
    redaction_applied: bool = False


class ConversationSession(BaseModel):
    """一次咨询会话；患者关联只允许使用经授权的匿名键，初复诊只来自可信元数据。"""

    session_id: str
    source_id: str | None = None
    anonymized_patient_ref: str | None = None
    consultation_round: ConsultationRound = "unknown"
    messages: list[Message] = Field(default_factory=list)
    imported_at: datetime | None = None


class PreprocessingStageReport(BaseModel):
    """单个预处理阶段的执行记录；failed 会阻断后续阶段。"""

    stage_name: str
    stage_version: str
    status: Literal["completed", "partial", "failed", "skipped"]
    issues: list[str] = Field(default_factory=list)


class RedactionSummary(BaseModel):
    """脱敏执行摘要；映射本体隔离保存，不进入 Agent 上下文或报告。"""

    ruleset_version: str
    masked_item_count: int = Field(ge=0)
    categories: list[str] = Field(default_factory=list)


class TranscriptSummary(BaseModel):
    """一条消息的转写摘要；供报告展示派生文本的来源与质量。"""

    message_id: str
    engine: str
    engine_version: str
    segment_count: int = Field(ge=0)
    average_confidence: float | None = Field(default=None, ge=0, le=1)


class PreprocessingReport(BaseModel):
    """一次预处理的完整报告；verdict 决定会话能否进入评价流程。"""

    session_id: str
    status: Literal["completed", "partial", "failed"]
    verdict: Literal["evaluable", "partially_evaluable", "not_evaluable"]
    stage_reports: list[PreprocessingStageReport] = Field(default_factory=list)
    redaction: RedactionSummary | None = None
    transcripts: list[TranscriptSummary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PreprocessedSession(BaseModel):
    """预处理产物：规范化会话 + 预处理报告，二者一起流转。"""

    session: ConversationSession
    report: PreprocessingReport


class TimeRange(BaseModel):
    """音视频片段的时间区间；用于证据跳转到原始媒体位置。"""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)


class ConversationEvidenceRef(BaseModel):
    """指向原会话消息的证据引用；音视频消息可附带媒体时间区间。"""

    message_ids: list[str]
    quote: str
    explanation: str
    media_time_ranges: list[TimeRange] = Field(default_factory=list)


class KnowledgeRef(BaseModel):
    """知识库来源引用；与会话证据分开，避免把规范材料误当成行为证据。"""

    source_id: str
    title: str
    excerpt: str
    version: str | None = None


class MemoryRef(BaseModel):
    """患者背景记忆引用；默认不启用，且不能作为医生行为评分的直接证据。"""

    memory_id: str
    anonymized_patient_ref: str
    summary: str


class HistorySessionRef(BaseModel):
    """历史会话来源引用；复诊历史检索结果按来源记录。"""

    session_id: str
    occurred_at: datetime | None = None
    source_id: str | None = None


class HistoricalMessageRef(BaseModel):
    """历史消息引用；只作背景注入，不能支撑本次医生行为评分。"""

    session_id: str
    message_id: str
    role: SpeakerRole
    content: str
    modality: Modality = "text"
    timestamp: datetime | None = None


class HistoryContext(BaseModel):
    """复诊历史上下文；与本次会话消息分区注入并持续标注来源。"""

    status: Literal["retrieved", "not_follow_up", "unavailable", "not_authorized"]
    source_sessions: list[HistorySessionRef] = Field(default_factory=list)
    messages: list[HistoricalMessageRef] = Field(default_factory=list)
    retrieval_trace_id: str | None = None


class RiskTrigger(BaseModel):
    """风险 Hook 候选；命中仅路由 D6 评价，不构成违规或风险结论。"""

    trigger_id: str
    category: str
    message_ids: list[str]
    rule_id: str
    rule_version: str
    status: Literal["candidate", "routed", "evaluated", "dismissed"] = "candidate"


class RunConfig(BaseModel):
    """一次评价运行的配置快照；随报告保存用于复现。"""

    language: str = "zh"
    rubric_version: str = "draft"
    output_schema_version: str = "0.1.0"


class AgentInput(BaseModel):
    """Agent 统一输入；只接收当前任务获准访问的 Skill、知识、记忆和历史上下文。"""

    session: ConversationSession
    history_context: HistoryContext | None = None
    selected_skill_ids: list[str] = Field(default_factory=list)
    knowledge_context: list[KnowledgeRef] = Field(default_factory=list)
    memory_context: list[MemoryRef] = Field(default_factory=list)
    risk_candidates: list[RiskTrigger] = Field(default_factory=list)
    run_config: RunConfig = Field(default_factory=RunConfig)


class Finding(BaseModel):
    """一个指标的评价结果；不适用、上下文不足或证据无效时 score 应为空。"""

    metric_id: str
    applicability: Literal["applicable", "not_applicable", "insufficient_context"] = "applicable"
    score: float | None = Field(default=None, ge=0, le=5)
    rationale: str
    evidence: list[ConversationEvidenceRef] = Field(default_factory=list)
    knowledge_refs: list[KnowledgeRef] = Field(default_factory=list)
    confidence_band: Literal["high", "medium", "low"] | None = None
    limitations: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Agent 的结构化执行结果；支持成功、部分成功和失败状态。"""

    agent_id: str
    status: Literal["completed", "partial", "failed"]
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None


class EvaluationReport(BaseModel):
    """评价报告数据结构；限制项携带预处理与证据核验问题。"""

    evaluation_id: str
    session_id: str
    status: Literal["completed", "partial", "failed"]
    agent_results: list[AgentResult] = Field(default_factory=list)
    summary: str = ""
    limitations: list[str] = Field(default_factory=list)
