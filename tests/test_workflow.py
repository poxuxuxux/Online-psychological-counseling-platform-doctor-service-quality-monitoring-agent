# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
import asyncio
from datetime import UTC, datetime

import pytest
from langgraph.errors import NodeCancelledError

from app.context.service import SessionContextManager, preprocess
from app.domain.models import Session
from app.team.tools import TeamTools
from tests.conftest import ScriptedModel


async def test_complete_graph_scoring_and_persistence(make_service, session):
    service, repo = await make_service()
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["session_type"] == "INITIAL"
    assert report["quality_profile"]["overall_score"] == 5
    assert report["risk"]["level"] == "low"
    stored = await repo.get_run(report["evaluation_id"])
    assert stored["next_stage"] == "done"
    assert "team_runtime" in stored["completed_stages"]
    assert await service.execute(report["evaluation_id"]) == report


async def test_late_message_wakes_completed_agent_and_revises(make_service, session):
    service, repo = await make_service(ScriptedModel(collaboration=True))
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    team = state["team"]
    assert len(team["messages"]) == 1
    assert team["messages"][0]["status"] == "PROCESSED"
    result = team["tasks"]["evaluator:D2"]["findings"]["D2.1"]
    assert result["revision_count"] == 1
    assert result["score"] == 4
    assert len(team["finding_history"]) == 3
    assert report["quality_profile"]["overall_score"] == 4.5


async def test_team_lead_arbitration_and_conflict_revision(make_service, session):
    service, repo = await make_service(ScriptedModel(conflict=True))
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["reviews_created"] == 1
    assert state["team"]["tasks"]["team_lead"]["kind"] == "team_lead"
    assert report["arbitration_status"] == "resolved"
    assert all(m["status"] == "PROCESSED" for m in state["team"]["messages"])
    assert report["quality_profile"]["overall_score"] == 4


async def test_history_identity_time_unknown_and_no_score_anchoring(make_service, session):
    model = ScriptedModel()
    service, repo = await make_service(model)
    first = await service.evaluate(session)
    later = session.model_copy(
        update={"session_id": "s2", "session_time": datetime(2026, 2, 1, tzinfo=UTC)}
    )
    second = await service.evaluate(later)
    assert second["session_type"] == "FOLLOW_UP"
    assert second["longitudinal"]["previous_evaluation_id"] == first["evaluation_id"]
    assert second["longitudinal"]["score_delta"] == 0
    other = later.model_copy(
        update={"session_id": "s3", "doctor_id": "other", "history_complete": False}
    )
    assert (await SessionContextManager(repo).route(preprocess(other)))["session_type"] == "UNKNOWN"
    # Future/current records cannot become prior history.
    assert not (await repo.history(preprocess(session)))
    for payload in model.payloads:
        if "task" in payload:
            assert "history" not in payload
            assert "latest_evaluation" not in payload


async def test_scoring_skips_independent_semantic_model_pass(make_service, session):
    model = ScriptedModel(invalid_checks=True)
    service, _ = await make_service(model)
    report = await service.evaluate(session)
    assert report["quality_profile"]["overall_score"] == 5
    assert report["verification_mode"] == "none"
    assert report["verification_results"] == []
    assert "evidence_validator" not in report["pipeline_stages"]
    assert not any(p.get("purpose") == "evidence_validation" for p in model.payloads)


async def test_no_model_never_fabricates_scores(make_service, session):
    model = ScriptedModel()
    model.configured = False
    service, _ = await make_service(model)
    report = await service.evaluate(session)
    assert report["status"] == "failed"
    assert report["quality_profile"]["overall_score"] is None
    assert sum(len(a["findings"]) for a in report["agent_results"]) == 2
    assert not model.payloads


async def test_budget_and_timeout_terminate(make_service, session):
    service, _ = await make_service(max_model_calls=1)
    report = await service.evaluate(session)
    assert report["team"]["model_call_count"] == 1
    assert report["quality_profile"]["overall_score"] is None

    class SlowModel(ScriptedModel):
        async def json(self, *args):
            await asyncio.sleep(2)

    service, _ = await make_service(SlowModel(), total_timeout=0.15)
    report = await service.evaluate(session)
    assert report["team"]["stop_reason"] == "total_timeout"


async def test_lease_and_resume_after_interruption(make_service, session):
    service, repo = await make_service()
    run = await service.create(session)
    assert await repo.claim(run, "other", 60)
    assert not await repo.claim(run, "duplicate", 60)
    await repo.release(run, "other")
    original = repo.checkpoint
    interrupted = False

    async def crash(state, owner):
        nonlocal interrupted
        await original(state, owner)
        if state.get("team", {}).get("messages") and not interrupted:
            interrupted = True
            raise asyncio.CancelledError

    service.model = ScriptedModel(collaboration=True)
    repo.checkpoint = crash
    with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
        await service.execute(run)
    repo.checkpoint = original
    report = await service.execute(run)
    state = await repo.get_run(run)
    assert len(state["team"]["messages"]) == 1
    assert state["team"]["messages"][0]["status"] == "PROCESSED"
    assert report["status"] == "completed"


async def test_tool_ownership_evidence_and_history_guards(make_service, session):
    service, repo = await make_service()
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    tools = TeamTools(service.settings, service.knowledge)
    with pytest.raises(ValueError, match="speaker/source"):
        await tools.execute(
            state,
            "evaluator:D1",
            "share_evidence",
            {"message_id": "m1", "speaker": "patient", "quote": "听起来你很难受"},
        )
    with pytest.raises(ValueError, match="contiguous"):
        await tools.execute(
            state,
            "evaluator:D1",
            "share_evidence",
            {"message_id": "m1", "speaker": "doctor", "quote": "医生不存在的原话"},
        )
    result = await tools.execute(
        state,
        "evaluator:D1",
        "get_previous_evaluations",
        {"metric_id": "D1.1", "reason": "Need history"},
    )
    assert result["status"] == "not_allowed_by_skill"
    finding = {
        k: v
        for k, v in state["team"]["tasks"]["evaluator:D2"]["findings"]["D2.1"].items()
        if k
        in {
            "metric_id",
            "status",
            "score",
            "reason",
            "evidence_ids",
            "claims",
            "review_rule_ids",
            "risk",
        }
    }
    with pytest.raises(ValueError, match="another evaluator"):
        await tools.execute(state, "evaluator:D1", "submit_evaluation", {"findings": [finding]})


async def test_immutable_input_and_duplicate_message_validation(make_service, session):
    _, repo = await make_service()
    await repo.save_session(preprocess(session))
    changed = session.model_copy(update={"doctor_id": "different"})
    with pytest.raises(ValueError, match="immutable"):
        await repo.save_session(preprocess(changed))
    payload = session.model_dump()
    payload["messages"].append(payload["messages"][0])
    with pytest.raises(ValueError, match="unique"):
        Session.model_validate(payload)
