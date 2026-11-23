# 环节：协商契约；用途：约束规划、初评、逐项反馈及Leader裁决的结构化输出。
from typing import Literal

from pydantic import Field

from app.domain.models import FindingInput, StrictModel


class Selection(StrictModel):
    metric_id: str
    reason: str = Field(min_length=1, max_length=1500)
    candidate_weight: float = Field(ge=0, allow_inf_nan=False)


class Exclusion(StrictModel):
    metric_id: str
    reason: str = Field(min_length=1, max_length=1500)


class Plan(StrictModel):
    context_summary: str = Field(min_length=1, max_length=2500)
    task_analysis: str = Field(min_length=1, max_length=2500)
    relevance_analysis: str = Field(min_length=1, max_length=2500)
    consistency_check: str = Field(min_length=1, max_length=2500)
    selected: list[Selection]
    excluded: list[Exclusion]


class InitialBatch(StrictModel):
    findings: list[FindingInput] = Field(min_length=1)


class Feedback(StrictModel):
    metric_id: str
    decision: Literal["agree", "disagree", "insufficient"]
    reason: str = Field(min_length=1, max_length=2500)
    evidence_ids: list[str]
    issue_type: Literal["none", "factual", "applicability", "anchor", "evidence", "rubric", "execution"]
    revised_finding: FindingInput | None = None


class FeedbackBatch(StrictModel):
    report_version: int = Field(ge=0)
    feedback: list[Feedback] = Field(min_length=1)


class Response(StrictModel):
    feedback_id: str
    disposition: Literal["accepted", "rejected", "partially_accepted"]
    reason: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str]


class LeaderItem(StrictModel):
    finding: FindingInput
    question: str = Field(min_length=1, max_length=2000)
    factual_resolution: Literal["resolved", "unresolved"]
    decision_method: Literal["provisional", "consensus", "evidence_adjudicated", "not_evaluable", "not_applicable"]
    responses: list[Response]


class LeaderBatch(StrictModel):
    report_version: int = Field(ge=0)
    items: list[LeaderItem] = Field(min_length=1)


def leader_batch_schema(*, final: bool) -> dict:
    """Expose only decision methods that the current workflow phase accepts."""
    schema = LeaderBatch.model_json_schema()
    item = schema["$defs"]["LeaderItem"]
    item["properties"]["factual_resolution"]["description"] = (
        "Whether facts/applicability are grounded, not whether agents agree or review has finished. "
        "At final adjudication unresolved requires NOT_EVALUABLE and score=null; "
        "a nonfinal contradictory candidate is pending review and cannot become a final consensus."
    )
    final_fact_rule = [{
        "if": {"properties": {"factual_resolution": {"const": "unresolved"}},
               "required": ["factual_resolution"]},
        "then": {"properties": {"finding": {
            "properties": {"status": {"const": "NOT_EVALUABLE"}, "score": {"type": "null"}},
            "required": ["status", "score"],
        }}},
    }]
    if final:
        item["allOf"] = final_fact_rule
    method = schema["$defs"]["LeaderItem"]["properties"]["decision_method"]
    method["enum"] = (["consensus", "evidence_adjudicated", "not_evaluable", "not_applicable"]
                      if final else ["provisional"])
    if not final:
        method["const"] = "provisional"
    method["description"] = (
        "Final decision method; must match finding status and evidence/consensus requirements."
        if final else "Always provisional for preliminary/revision reports, including unscored or not applicable items."
    )
    return schema
