"""功能：定义多模态会话、预处理报告、历史上下文、风险候选、质量画像、仲裁与报告等跨模块契约。"""

from datetime import datetime
from typing import Literal
from uuid import uuid4

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
    rule_ids: list[str] = Field(default_factory=list)


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

    finding_id: str = Field(default_factory=lambda: f"finding-{uuid4()}")
    metric_id: str
    metric_version: str | None = None
    attempt: int = Field(default=0, ge=0, le=1)
    supersedes_finding_id: str | None = None
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


class FactClaim(BaseModel):
    """从 Finding 中拆出的最小可核验事实；复杂条件保留在 statement 与 qualifiers。"""

    claim_id: str = Field(default_factory=lambda: f"claim-{uuid4()}")
    finding_id: str
    claim_type: Literal["observed_behavior", "absence", "applicability", "score_basis"]
    statement: str
    subject_role: SpeakerRole | None = None
    behavior: str | None = None
    object_text: str | None = None
    time_scope: str | None = None
    negated: bool = False
    qualifiers: list[str] = Field(default_factory=list)


class ClaimVerification(BaseModel):
    """一条事实主张的核验结论；证据不足与明确反证分开表达。"""

    claim_id: str
    status: Literal["supported", "contradicted", "insufficient_evidence"]
    supporting_evidence: list[ConversationEvidenceRef] = Field(default_factory=list)
    contradicting_evidence: list[ConversationEvidenceRef] = Field(default_factory=list)
    rationale: str = ""


class EvidenceVerificationResult(BaseModel):
    """统一核验结果：原文定位、事实核验、适用性与评分锚点分别记录。"""

    verification_id: str = Field(default_factory=lambda: f"verification-{uuid4()}")
    finding_id: str
    verifier_agent_id: str = "evidence_verification"
    reference_status: Literal[
        "valid", "missing", "quote_mismatch", "source_mismatch", "uncertain"
    ]
    claims: list[FactClaim] = Field(default_factory=list)
    claim_results: list[ClaimVerification] = Field(default_factory=list)
    reference_conflict: bool = False
    applicability_status: Literal["matched", "mismatched", "uncertain"] = "uncertain"
    rubric_status: Literal["matched", "mismatched", "uncertain"] = "uncertain"
    support_status: Literal["supported", "partial", "unsupported", "uncertain"]
    issues: list[str] = Field(default_factory=list)
    revision_request: str | None = None
    verifier_version: str | None = None


class MetricScore(BaseModel):
    """单指标评分汇总输入；指标 ID 与权重以版本化 Skill 发布的指标体系为准。"""

    metric_id: str
    dimension_id: str
    score: float | None = Field(default=None, ge=0, le=5)
    weight: float = Field(default=1.0, gt=0)
    applicability: Literal["applicable", "not_applicable", "insufficient_context"] = "applicable"
    agent_id: str | None = None


class DimensionProfile(BaseModel):
    """一个维度的画像：加权维度分与覆盖率；覆盖率不达标时 score 为空。"""

    dimension_id: str
    name: str
    score: float | None = Field(default=None, ge=0, le=5)
    coverage: float = Field(default=0.0, ge=0, le=1)
    metric_scores: list[MetricScore] = Field(default_factory=list)


class QualityProfile(BaseModel):
    """6 维质量画像与总评分；全部由确定性汇总器计算，LLM 不得改写。"""

    dimensions: list[DimensionProfile] = Field(default_factory=list)
    overall_score: float | None = Field(default=None, ge=0, le=5)
    overall_coverage: float = Field(default=0.0, ge=0, le=1)
    coverage_gate_passed: bool = False


class ConflictCase(BaseModel):
    """确定性冲突检测的输出；语义复核与裁决交给分歧仲裁 Agent。"""

    conflict_id: str
    kind: Literal["cross_dimension", "score_revision", "verification_dispute", "rule_mismatch"]
    metric_ids: list[str] = Field(default_factory=list)
    description: str


class ArbitrationDecision(BaseModel):
    """仲裁 Agent 对单个冲突的裁决；不重写分数，只选择保留结论或转人工。"""

    conflict_id: str
    status: Literal["resolved", "unresolved", "not_needed"]
    adopted: Literal["initial", "re_evaluated", "verification", "manual_review"] | None = None
    rationale: str = ""
    re_evaluation_metric_ids: list[str] = Field(default_factory=list)
    requires_manual_review: bool = False


class ImprovementSuggestion(BaseModel):
    """总结 Agent 生成的改进意见；基于评分锚点，不构成临床督导结论。"""

    target_id: str
    level: Literal["metric", "dimension", "overall"]
    suggestion: str
    based_on: Literal["score_anchor", "risk_case", "coverage_gap"] = "score_anchor"
    related_evidence: list[ConversationEvidenceRef] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """评价报告数据结构；限制项携带预处理与证据核验问题，画像与改进意见随报告保留。"""

    evaluation_id: str
    session_id: str
    status: Literal["completed", "partial", "failed"]
    agent_results: list[AgentResult] = Field(default_factory=list)
    verification_results: list[EvidenceVerificationResult] = Field(default_factory=list)
    summary: str = ""
    limitations: list[str] = Field(default_factory=list)
    quality_profile: QualityProfile | None = None
    improvements: list[ImprovementSuggestion] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    summary_status: Literal["completed", "partial", "failed", "not_configured", "skipped"] | None = None
    arbitration_status: Literal["not_needed", "resolved", "unresolved", "not_configured"] | None = None
