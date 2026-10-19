# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
import json

import pytest
from pydantic import ValidationError

from app.domain.ports import ModelUnavailable
from app.evaluation.validation import FindingCheck
from app.rubrics.payload import metric_payload
from tests.conftest import ScriptedModel


async def test_positive_notes_do_not_create_manual_review(make_service, session):
    class NotesModel(ScriptedModel):
        async def json(self, system, payload, schema):
            result = await super().json(system, payload, schema)
            for check in result.get("checks", []):
                check["notes"] = ["The score is supported; wording could be more concise."]
            return result

    service, _ = await make_service(NotesModel())
    report = await service.evaluate(session)
    assert not report["review_required"]
    assert report["quality_profile"]["overall_score"] == 5


def test_arbitrary_prose_is_not_a_blocking_code():
    with pytest.raises(ValidationError):
        FindingCheck.model_validate(
            {
                "finding_id": "f",
                "support_status": "supported",
                "applicability_status": "matched",
                "rubric_status": "matched",
                "claim_results": [],
                "issues": ["Score is supported"],
            }
        )


async def test_owner_repairs_score_and_independent_validator_rechecks(make_service, session):
    class RepairModel(ScriptedModel):
        async def json(self, system, payload, schema):
            if payload.get("purpose") == "evaluation_repair":
                return {"findings": [{**f, "score": 4} for f in payload["findings"]]}
            result = await super().json(system, payload, schema)
            if payload.get("purpose") == "evidence_validation":
                for f, check in zip(payload["findings"], result["checks"], strict=True):
                    if f["score"] == 5:
                        check.update(rubric_status="mismatched", issues=["score_anchor_mismatch"])
            return result

    service, repo = await make_service(RepairModel())
    report = await service.evaluate(session)
    assert report["quality_profile"]["overall_score"] == 4
    state = await repo.get_run(report["evaluation_id"])
    assert len(state["team"]["validation_repairs"]) == 2
    assert len(state["team"]["finding_history"]) == 4
    assert all(
        f["revision_count"] == 1
        for t in state["team"]["tasks"].values()
        for f in t["findings"].values()
    )


async def test_provider_errors_stop_after_two_attempts_per_agent(make_service, session):
    class FailedModel(ScriptedModel):
        async def json(self, *args):
            raise ModelUnavailable("model_timeout")

    service, repo = await make_service(FailedModel())
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["model_calls"] == 4
    assert all(t["model_errors"] == 2 for t in state["team"]["tasks"].values())


def test_projection_preserves_yaml_rules_and_omits_duplicate_instruction(catalog):
    spec = catalog.metrics["D1.1"]
    projection = metric_payload(spec)
    assert projection["anchors"] == spec["anchors"]
    assert projection["manual_review"] == spec["manual_review"]
    assert "instructions" not in projection
    assert len(json.dumps(projection)) < len(json.dumps(spec))
