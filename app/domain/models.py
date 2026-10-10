"""功能：定义会话、证据、Agent 结果和报告等跨模块共用的数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """规范化单条对话；导入时应使用匿名 ID，避免保留不必要的身份信息。"""

    message_id: str
    role: Literal["doctor", "patient", "system", "unknown"]
    content: str
    sequence: int = Field(ge=0)


class ConversationSession(BaseModel):
    """一次咨询会话；患者关联只允许使用经授权的匿名键。"""

    session_id: str
    messages: list[Message]
    anonymized_patient_ref: str | None = None


class ConversationEvidenceRef(BaseModel):
    """指向原会话消息的证据引用；用于让评分能够被复核和追溯。"""

    message_ids: list[str]
    quote: str
    explanation: str


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


class AgentInput(BaseModel):
    """Agent 统一输入；只接收当前任务获准访问的 Skill、知识和记忆上下文。"""

    session: ConversationSession
    selected_skill_ids: list[str] = Field(default_factory=list)
    knowledge_context: list[KnowledgeRef] = Field(default_factory=list)
    memory_context: list[MemoryRef] = Field(default_factory=list)


class Finding(BaseModel):
    """一个指标的评价结果；证据不足时 score 应为空并说明限制。"""

    metric_id: str
    score: float | None = Field(default=None, ge=0, le=5)
    rationale: str
    evidence: list[ConversationEvidenceRef] = Field(default_factory=list)
    knowledge_refs: list[KnowledgeRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Agent 的结构化执行结果；支持成功、部分成功和失败状态。"""

    agent_id: str
    status: Literal["completed", "partial", "failed"]
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None


class EvaluationReport(BaseModel):
    """评价报告数据结构；后续需附上指标/Skill 版本和执行配置快照。"""

    evaluation_id: str
    session_id: str
    status: Literal["completed", "partial", "failed"]
    agent_results: list[AgentResult] = Field(default_factory=list)
    summary: str = ""
    limitations: list[str] = Field(default_factory=list)
