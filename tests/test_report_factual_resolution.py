"""Pending hypotheses enter discussion but cannot become final scores."""
import pytest

from app.team.post_initial_protocol import PROTOCOL_V2
from app.team.protocol_models import leader_batch_schema
from tests.test_post_initial import PostInitialModel


def test_final_schema_enforces_fact_dependency():
    assert "allOf" not in leader_batch_schema(final=False)["$defs"]["LeaderItem"]
    rule = leader_batch_schema(final=True)["$defs"]["LeaderItem"]["allOf"][0]
    assert rule["then"]["properties"]["finding"]["properties"] == {
        "status": {"const": "NOT_EVALUABLE"}, "score": {"type": "null"}}


@pytest.mark.parametrize("never_resolved", [False, True])
async def test_pending_p0_cannot_become_early_consensus(make_service, session, never_resolved):
    model = PostInitialModel(selected=["D1.1", "D2.1"])
    original = model.json

    async def conflicting(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"].startswith("leader_") and "items" in result:
            for item in result["items"]:
                if (item["finding"]["metric_id"] == "D1.1"
                        and (payload["purpose"] == "leader_preliminary" or never_resolved)):
                    item["factual_resolution"] = "unresolved"
        return result

    model.json = conflicting
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    p0 = state["team"]["reports"][0]["items"]["D1.1"]
    assert p0["factual_resolution"] == "unresolved"
    assert p0["finding"]["score"] == 4
    assert "待核对候选" in p0["question"]
    assert sum(p["purpose"] == "leader_preliminary" for p in model.payloads) == 1
    assert any(p["purpose"] == "leader_revision" for p in model.payloads)
    if never_resolved:
        assert report["team"]["stop_reason"] == "metric_submission_rejected"
        assert report["quality_profile"]["overall_score"] is None
        assert state["team"]["final_findings"]["D1.1"]["score"] is None
    else:
        assert report["status"] == "completed"
        assert report["quality_profile"]["overall_score"] == 4
        assert report["collaboration"]["round_count"] == 2


async def test_revision_step_budget_is_per_version(make_service, session):
    model = PostInitialModel(selected=["D1.1"])
    model.mode = "dissent"
    service, _ = await make_service(model, team_protocol=PROTOCOL_V2, max_steps=1)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["collaboration"]["round_count"] == 3


@pytest.mark.parametrize("stage", ["leader_preliminary", "leader_revision", "leader_final"])
async def test_leader_repeated_absence_with_incomplete_observation_keeps_empty_score(make_service, session, stage):
    model = PostInitialModel(selected=["D1.1"])
    model.mode = "dissent"
    original = model.json
    attempts = 0

    async def absence(system, payload, schema):
        nonlocal attempts
        result = await original(system, payload, schema)
        if payload["purpose"] == stage:
            attempts += 1
            for item in result["items"]:
                item["finding"]["claims"][0]["polarity"] = "absent"
        return result

    model.json = absence
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session.model_copy(update={"observation_complete": False}))
    state = await repo.get_run(report["evaluation_id"])
    assert report["team"]["stop_reason"] == "completed"
    events = [e for e in state["team"]["events"] if e["action"] == "leader_absence_unresolved"]
    assert events and all(e["detail"]["purpose"] == stage for e in events)
    assert attempts >= 3
    empty = [r["items"]["D1.1"] for r in state["team"]["reports"]
             if r["items"]["D1.1"]["finding"]["status"] == "NOT_EVALUABLE"]
    assert empty and all(r["finding"]["score"] is None and not r["finding"]["claims"] for r in empty)
    if stage == "leader_final":
        assert state["team"]["final_findings"]["D1.1"]["score"] is None
