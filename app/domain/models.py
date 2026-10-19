# 环节：领域契约层；用途：定义业务数据模型与可替换端口，不依赖具体基础设施。
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def known_fields_only(cls, data):
    """Drop model-invented keys at the parse boundary; nothing unvalidated passes through."""
    return (
        {k: v for k, v in data.items() if k in cls.model_fields} if isinstance(data, dict) else data
    )


def _known_fields_only(cls, data):
    return known_fields_only(cls, data)


def _coerce_score(value):
    """LLMs often emit integral floats or digit strings for scores."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    role: Literal["doctor", "patient", "system", "unknown"] = "unknown"
    content: str = Field(max_length=20000)
    sequence: int = Field(ge=0)
    timestamp: datetime | None = None
    modality: Literal["text", "audio", "video"] = "text"
    message_kind: Literal["dialogue", "system_notification", "non_dialogue", "unknown"] = "dialogue"
    redaction_applied: bool = False


class Session(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    patient_id: str | None = Field(default=None, max_length=200)
    doctor_id: str | None = Field(default=None, max_length=200)
    anonymized_patient_ref: str | None = None
    source_id: str | None = None
    session_time: datetime | None = None
    imported_at: datetime | None = None
    history_complete: bool = False
    observation_complete: bool = False
    consultation_round: Literal["initial", "follow_up", "unknown"] = "unknown"
    service_context: dict = Field(default_factory=dict)
    messages: list[Message] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_session(self):
        for values in ([m.message_id for m in self.messages], [m.sequence for m in self.messages]):
            if len(values) != len(set(values)):
                raise ValueError("Message IDs and sequence numbers must be unique")
        times = [self.session_time, *[m.timestamp for m in self.messages]]
        if any(t is not None and t.utcoffset() is None for t in times):
            raise ValueError("Times must include a timezone")
        if sum(len(m.content) for m in self.messages) > 120000:
            raise ValueError("Dialogue exceeds 120000 characters; split at session boundaries")
        self.patient_id = self.patient_id or self.anonymized_patient_ref
        return self


class EvidenceInput(StrictModel):
    message_id: str
    speaker: Literal["doctor", "patient", "system", "unknown"]
    quote: str = Field(min_length=1, max_length=10000)


class Claim(StrictModel):
    behavior: str = Field(min_length=1, max_length=200)
    subject: Literal["doctor", "patient"] = "doctor"
    polarity: Literal["present", "absent"]
    scope: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def adapt_model_output(cls, data):
        return _known_fields_only(cls, data)


class FindingInput(StrictModel):
    metric_id: str
    status: Literal["EVALUATED", "NOT_APPLICABLE", "NOT_EVALUABLE"]
    score: int | None = Field(default=None, ge=0, le=5, strict=True)
    reason: str = Field(min_length=1, max_length=5000)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list, max_length=12)
    review_rule_ids: list[str] = Field(default_factory=list)
    risk: Literal["none", "service_gap", "serious_service_risk"] = "none"

    @model_validator(mode="before")
    @classmethod
    def adapt_model_output(cls, data):
        if isinstance(data, dict):
            # Observed provider deviation: rationale instead of the required reason.
            if not data.get("reason") and isinstance(data.get("rationale"), str):
                data = {**data, "reason": data["rationale"]}
            if "score" in data:
                data = {**data, "score": _coerce_score(data["score"])}
        return _known_fields_only(cls, data)

    @model_validator(mode="after")
    def score_matches_status(self):
        if self.status != "EVALUATED" and self.score is not None:
            raise ValueError("Only EVALUATED findings may contain scores")
        if self.status == "EVALUATED" and self.score is None:
            raise ValueError("EVALUATED requires a score")
        return self


class ToolCall(StrictModel):
    name: Literal[
        "read_skill",
        "get_dialogue",
        "get_evidence",
        "search_knowledge",
        "get_session_context",
        "get_previous_evaluations",
        "time_calculator",
        "share_evidence",
        "send_message",
        "get_messages",
        "acknowledge_message",
        "request_review",
        "submit_review",
        "submit_evaluation",
        "wait",
        "finish",
    ]
    arguments: dict = Field(default_factory=dict)


class Decision(StrictModel):
    # Short action justification, not private chain-of-thought.
    rationale: str = Field(min_length=1, max_length=1000)
    tool_call: ToolCall

    @model_validator(mode="before")
    @classmethod
    def adapt_model_output(cls, data):
        # Observed provider deviation: flat {"tool"/"name", "arguments"} instead of tool_call.
        if isinstance(data, dict) and "tool_call" not in data:
            if isinstance(data.get("findings"), list):
                data = {
                    **data,
                    "tool_call": {
                        "name": "submit_evaluation",
                        "arguments": {"findings": data["findings"], "complete": True},
                    },
                }
            name = data.get("tool") if isinstance(data.get("tool"), str) else data.get("name")
            if isinstance(name, str):
                data = {
                    **data,
                    "tool_call": {"name": name, "arguments": data.get("arguments", {})},
                }
        if isinstance(data, dict) and "tool_call" in data and not data.get("rationale"):
            data = {**data, "rationale": "Execute the selected tool for the assigned task."}
        return _known_fields_only(cls, data)


MESSAGE_TYPES = {
    "EVIDENCE_SHARE",
    "CLARIFICATION_REQUEST",
    "CONFLICT_REPORT",
    "REVIEW_REQUEST",
    "RISK_ALERT",
}
