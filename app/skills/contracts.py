"""Metric Skill v1 authoring contract shared with the indicator-rule author."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RuleText = Annotated[str, Field(min_length=1)]
StrictScore = Annotated[int, Field(strict=True)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApplicabilityRules(ContractModel):
    applicable_when: list[RuleText] = Field(min_length=1)
    not_applicable_when: list[RuleText] = Field(min_length=1)
    insufficient_context_when: list[RuleText] = Field(min_length=1)


class EvidenceRules(ContractModel):
    allowed_sources: list[
        Literal["current_dialogue", "current_intake", "service_events", "tool_facts"]
    ] = Field(min_length=1)
    required_checks: list[RuleText] = Field(min_length=1)
    forbidden_uses: list[RuleText] = Field(min_length=1)


class ScoreAnchor(ContractModel):
    score: int = Field(ge=0, le=5, strict=True)
    criteria: str = Field(min_length=1)


class ManualReviewRule(ContractModel):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    condition: str = Field(min_length=1)


class MetricSkillSpec(ContractModel):
    schema_version: Literal["1.0"]
    metric_id: str = Field(pattern=r"^D[1-6]\.[1-5]$")
    name: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$")
    status: Literal["draft", "published"]
    owner: Literal["professional_service", "process_response", "empathy_relationship"]
    definition: str = Field(min_length=1)
    applicability: ApplicabilityRules
    evidence: EvidenceRules
    score_values: list[StrictScore] = Field(min_length=5, max_length=6)
    anchors: list[ScoreAnchor]
    manual_review: list[ManualReviewRule] = Field(min_length=1)
    required_tools: list[Literal["evidence_locator", "time_calculator"]] = Field(
        default_factory=lambda: ["evidence_locator"]
    )

    @model_validator(mode="after")
    def validate_rules(self):
        if self.score_values not in [list(range(1, 6)), list(range(6))]:
            raise ValueError("score_values must explicitly be [1,2,3,4,5] or [0,1,2,3,4,5]")
        scores = [anchor.score for anchor in self.anchors]
        if len(scores) != len(set(scores)) or any(s not in self.score_values for s in scores):
            raise ValueError("Duplicate or out-of-range score anchors")
        if self.status == "published" and sorted(scores) != self.score_values:
            raise ValueError("Published Skill must define every score anchor")
        ids = [rule.rule_id for rule in self.manual_review]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate manual-review rule IDs")
        return self
