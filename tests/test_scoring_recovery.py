# 环节：评分回归测试；用途：验证真实目录、部分提交、执行诊断和有界补评。
import copy

import pytest

from app.config import Settings
from app.domain.ports import ModelUnavailable
from app.evaluation.analytics import overview
from app.evaluation.monitoring import _scored
from app.evaluation.scoring import report_has_score
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.team.conflicts import finalize_conflicts
from app.team.runtime import TeamRuntime
from app.team.state import initialize_team
from app.team.tools import TOOL_HELP, TeamTools
from tests.conftest import ScriptedModel


def finding(mid, **changes):
    return {"metric_id": mid, "status": "EVALUATED", "score": 4,
            "reason": "Observed doctor response", "evidence_ids": ["e-m1"],
            "claims": [{"subject": "doctor", "behavior": "responds", "polarity": "present",
                        "scope": "m1", "statement": "Doctor responds", "evidence_ids": ["e-m1"]}],
            "review_rule_ids": [], "risk": "none", **changes}


def real_state():
    catalog = SkillCatalog(Settings().skill_dir)
    state = {"run_id": "memory", "skills": catalog.snapshot(),
             "session": {"observation_complete": True},
             "team": initialize_team(catalog.snapshot(), "memory")}
    state["team"]["evidence"]["e-m1"] = {"message_id": "m1", "original_text": "Source"}
    for task in state["team"]["tasks"].values():
        task["skills_read"] = True
    return state


def test_partial_batch_preserves_good_siblings_and_returns_field_errors():
    state = real_state()
    tools = TeamTools(Settings(), None)
    bad = finding("D3.1", evidence_ids=["unknown"])
    malformed = {"metric_id": "D3.2", "applicability": "applicable", "score": 4,
                 "rationale": "Legacy fields must be corrected, not guessed"}
    result = tools.submit(state, "evaluator:D1", {
        "findings": [finding("D1.1"), bad, malformed], "complete": True})
    assert result["accepted"] == ["D1.1"]
    assert [f["metric_id"] for f in result["rejected"]] == ["D3.1", "D3.2"]
    assert result["rejected"][1]["fields"] == [{"path": ["status"], "type": "missing"}]
    task = state["team"]["tasks"]["evaluator:D1"]
    assert list(task["findings"]) == ["D1.1"]
    assert task["status"] != "COMPLETED"
    corrected = tools.submit(state, "evaluator:D1", {"findings": [finding("D3.1"), finding("D3.2")]})
    assert not corrected["rejected"]
    assert not task["submission_errors"]
    tools.submit(state, "evaluator:D1", {"findings": [finding("D1.1")]})
    assert task["findings"]["D1.1"]["revision_count"] == 0
    assert len(state["team"]["finding_history"]) == 3


def test_duplicate_and_foreign_metrics_do_not_discard_other_results():
    state = real_state()
    result = TeamTools(Settings(), None).submit(state, "evaluator:D1", {
        "findings": [finding("D1.1"), finding("D1.1"), finding("D2.1"), finding("D3.1")]})
    assert result["accepted"] == ["D3.1"]
    assert len(result["rejected"]) == 3
    assert not state["team"]["tasks"]["evaluator:D2"]["findings"]


def test_incomplete_observation_still_accepts_positive_evidence():
    state = real_state()
    state["session"]["observation_complete"] = False
    absent = finding("D3.1")
    absent["claims"][0]["polarity"] = "absent"
    result = TeamTools(Settings(), None).submit(state, "evaluator:D1", {
        "findings": [finding("D1.1"), absent]})
    assert result["accepted"] == ["D1.1"]
    assert "complete observation" in result["rejected"][0]["error"]


def test_arbitration_can_resolve_when_only_mistaken_side_revises():
    state = real_state()
    tools = TeamTools(Settings(), None)
    tools.submit(state, "evaluator:D1", {"findings": [finding("D1.1"), finding("D3.1")]})
    owned = state["team"]["tasks"]["evaluator:D1"]["findings"]
    state["team"]["conflicts"]["c"] = {"metric_ids": ["D1.1", "D3.1"],
        "finding_ids": [f["finding_id"] for f in owned.values()], "status": "OPEN",
        "review": {"decision": "revise"}}
    finalize_conflicts(state["team"])
    assert state["team"]["conflicts"]["c"]["status"] == "UNRESOLVED"
    tools.submit(state, "evaluator:D1", {"findings": [finding("D3.1", score=3)]})
    finalize_conflicts(state["team"])
    assert state["team"]["conflicts"]["c"]["status"] == "RESOLVED"


class SmallBatchModel(ScriptedModel):
    """Exercises the complete graph against all 18 production metric packages."""
    async def json(self, system, payload, schema):
        self.payloads.append(payload)
        if payload["task"]["kind"] == "team_lead":
            return self.action("assess_conflicts", conflicts=[], reason="No source conflicts")
        items = []
        for mid in payload["suggested_metric_ids"]:
            blocked = payload["frozen_skills"][mid].get("scoring_blockers", [])
            items.append(finding(mid, status="NOT_EVALUABLE", score=None, claims=[],
                                 evidence_ids=[], review_rule_ids=blocked) if blocked else finding(mid))
        return self.action("submit_evaluation", findings=items, complete=True)


async def test_production_catalog_total_survives_d2_exclusions(make_service, session):
    model = SmallBatchModel()
    service, repo = await make_service(model)
    service.catalog = SkillCatalog(Settings().skill_dir)
    service.knowledge = SkillKnowledgeSource(service.catalog)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert not report["review_required"]
    assert report["quality_profile"]["overall_score"] == 4
    assert report["quality_profile"]["evaluated_count"] == 16
    assert len(report["quality_profile"]["score_exclusions"]) == 2
    assert report_has_score(report) and _scored(report)
    summary = overview([report], service.catalog, 30, "sqlite")
    assert summary["counts"]["scored"] == 1
    assert summary["average_total"] == 80
    assert all(len(p["suggested_metric_ids"]) <= 2 for p in model.payloads)
    state = await repo.get_run(report["evaluation_id"])
    assert state["completion"]["complete"]
    for agent in report["agent_results"]:
        for item in agent["findings"]:
            if item["metric_id"].startswith("D2."):
                assert item["outcome"] == "configuration_blocked"


async def test_failures_are_not_evidence_shortages_and_retry_retains_success(make_service, session):
    class FailingModel(ScriptedModel):
        async def json(self, system, payload, schema):
            if payload["task"]["assigned_agent"] == "evaluator:D2":
                raise ModelUnavailable("model_timeout")
            return await super().json(system, payload, schema)

    service, repo = await make_service(FailingModel())
    failed = await service.evaluate(session)
    before = copy.deepcopy(await repo.get_run(failed["evaluation_id"]))
    missing = next(a for a in failed["agent_results"] if a["agent_id"] == "evaluator:D2")
    assert missing["findings"][0]["outcome"] == "execution_failed"
    assert missing["findings"][0]["failure_code"] == "model_timeout"
    retry = await service.retry_incomplete(failed["evaluation_id"])
    pending = await repo.get_run(retry)
    assert pending["team"]["tasks"]["evaluator:D1"]["status"] == "COMPLETED"
    assert not pending["team"]["tasks"]["evaluator:D2"]["findings"]
    service.model = ScriptedModel()
    result = await service.execute(retry)
    assert result["status"] == "completed"
    assert result["parent_evaluation_id"] == failed["evaluation_id"]
    assert all(p["task"]["assigned_agent"] != "evaluator:D1" for p in service.model.payloads)
    assert (await repo.get_run(failed["evaluation_id"]))["report"] == before["report"]
    with pytest.raises(ValueError, match="already complete"):
        await service.retry_incomplete(retry)


async def test_truncation_shrinks_batch_before_terminating(make_service, session):
    class TruncatedModel(ScriptedModel):
        async def json(self, system, payload, schema):
            task = payload["task"]
            if task["assigned_agent"] == "evaluator:D1" and task["steps"] < 2:
                self.payloads.append(payload)
                raise ModelUnavailable("model_truncated_response")
            return await super().json(system, payload, schema)

    model = TruncatedModel()
    service, _ = await make_service(model)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    d1 = [p for p in model.payloads if p["task"]["assigned_agent"] == "evaluator:D1"]
    assert d1[0]["submission_batch_size"] == 2
    assert d1[1]["submission_batch_size"] == 1


async def test_failed_lead_keeps_scores_but_exposes_unfinished_review(make_service, session):
    class FailedLead(ScriptedModel):
        async def json(self, system, payload, schema):
            if payload["task"]["kind"] == "team_lead":
                raise ModelUnavailable("model_timeout")
            return await super().json(system, payload, schema)

    service, _ = await make_service(FailedLead())
    report = await service.evaluate(session)
    assert report["status"] == "partial"
    assert report["review_required"]
    assert not report["collaboration_complete"]
    assert report["quality_profile"]["overall_score"] == 5
    assert report_has_score(report)


async def test_reported_concern_blocks_total_when_lead_fails(make_service, session):
    class ReportedConcern(ScriptedModel):
        async def json(self, system, payload, schema):
            task = payload["task"]
            if task["kind"] == "team_lead":
                raise ModelUnavailable("model_timeout")
            if task["assigned_agent"] == "evaluator:D1" and not any(
                o["tool"] == "request_review" for o in task["observations"]
            ):
                return self.action("request_review", metric_ids=["D1.1", "D2.1"], reason="Check source")
            return await super().json(system, payload, schema)

    service, _ = await make_service(ReportedConcern())
    report = await service.evaluate(session)
    assert report["quality_profile"]["overall_score"] is None
    assert not report_has_score(report)


def test_all_production_rules_use_current_contract_and_real_tools():
    catalog = SkillCatalog(Settings().skill_dir)
    for spec in catalog.metrics.values():
        assert set(spec["required_tools"]) <= set(TOOL_HELP)
        assert "按后端结构返回每个分派指标结果：metric_id、applicability" not in spec["instructions"]
        assert "evidence_ids、claims" in spec["instructions"]
        assert spec["weight"] == 1


async def test_long_allowed_message_has_advertised_evidence_id(make_service, session):
    service, _ = await make_service()
    message = session.messages[1].model_copy(update={"content": "a" * 15000})
    session = session.model_copy(update={"messages": [session.messages[0], message]})
    from app.context.service import preprocess
    state = {"run_id": "test", "session": preprocess(session), "skills": service.catalog.snapshot(),
             "team": initialize_team(service.catalog.snapshot(), "test")}
    state["team"]["active_agents"] = ["evaluator:D1"]
    runtime = TeamRuntime(service.settings, service.model, TeamTools(service.settings, None), None)
    await runtime.observe({"data": state})
    assert len(state["team"]["evidence"]["e-m1"]["original_text"]) == 15000


async def test_real_evidence_gap_is_not_automatically_retried(make_service, session):
    class MissingContext(ScriptedModel):
        async def json(self, system, payload, schema):
            if payload["task"]["kind"] == "evaluator":
                return self.action("submit_evaluation", complete=True, findings=[
                    finding(mid, status="NOT_EVALUABLE", score=None, evidence_ids=[], claims=[],
                            review_rule_ids=["source_incomplete"])
                    for mid in payload["task"]["metric_ids"]])
            return await super().json(system, payload, schema)

    service, _ = await make_service(MissingContext())
    report = await service.evaluate(session)
    assert report["collaboration_complete"]
    assert report["quality_profile"]["overall_score"] is None
    assert all(f["outcome"] == "insufficient_evidence"
               for a in report["agent_results"] for f in a["findings"])
    with pytest.raises(ValueError, match="already complete"):
        await service.retry_incomplete(report["evaluation_id"])


async def test_stranded_wait_is_recovered_with_existing_budget(make_service, session):
    class WaitingModel(ScriptedModel):
        async def json(self, system, payload, schema):
            task = payload["task"]
            if task["kind"] == "evaluator" and task["findings"] and not task.get("wait_recovered"):
                return self.action("wait")
            return await super().json(system, payload, schema)

    service, repo = await make_service(WaitingModel())
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    state = await repo.get_run(report["evaluation_id"])
    assert any(e["action"] == "recover_stranded_wait" for e in state["team"]["events"])
