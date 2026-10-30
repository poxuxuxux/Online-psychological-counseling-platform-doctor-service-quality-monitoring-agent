# 环节：新版协议回归；用途：验证权重约束、盲评、三轮反馈、逐条异议处理和真实裁决门槛。
import asyncio
import copy
import math
import random

import pytest
from langgraph.errors import NodeCancelledError

from app.config import Settings
from app.domain.ports import ModelUnavailable
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.team.lead_protocol import PROTOCOL
from app.team.message_bus import MessageBus
from app.team.weights import bounded_weights


def finding(mid, score=4, **changes):
    return {"metric_id": mid, "status": "EVALUATED", "score": score,
            "reason": "原文中医生回应了患者的体验，按所给锚点评价。", "evidence_ids": ["e-m1"],
            "claims": [{"subject": "doctor", "behavior": "responds", "polarity": "present",
                        "scope": "m1", "statement": "医生回应患者。", "evidence_ids": ["e-m1"]}],
            "review_rule_ids": [], "risk": "none", **changes}


class ProtocolModel:
    configured = True

    def __init__(self, mode="agree", selected=None):
        self.mode, self.selected = mode, selected
        self.payloads = []
        self.invalid_sent = False

    async def json(self, system, payload, schema):
        self.payloads.append(copy.deepcopy(payload))
        purpose = payload["purpose"]
        mids = payload["requested_metric_ids"]
        if purpose == "leader_plan":
            chosen = mids if self.selected is None else self.selected
            return {"context_summary": "当前会话", "task_analysis": "回应本次需求", "relevance_analysis": "按患者任务",
                    "consistency_check": "不按表现赋权", "selected": [
                        {"metric_id": mid, "reason": "本次任务相关", "candidate_weight": 99 if i == 0 else 1}
                        for i, mid in enumerate(chosen)], "excluded": [
                        {"metric_id": mid, "reason": "本次任务未选择"} for mid in mids if mid not in chosen]}
        agent = payload["task"]["assigned_agent"]
        if purpose == "initial_evaluation":
            assert "e-m1" in payload["available_evidence_ids"]
            assert all(m["evidence_id"] == "e-" + m["message_id"] for m in payload["dialogue"]["messages"])
            if self.mode == "timeout" and agent == "evaluator:empathy":
                raise ModelUnavailable("model_timeout")
            items = [finding(mid, 1 if self.mode in {"dissent", "false_consensus", "unresolved", "persuaded"}
                             and agent == "evaluator:effectiveness" else 4) for mid in mids]
            if self.mode == "partial" and not self.invalid_sent and agent == "evaluator:effectiveness":
                self.invalid_sent = True
                items[-1]["evidence_ids"] = ["unknown"]
            return {"findings": items}
        if purpose.startswith("evaluator_feedback_"):
            responses = []
            for mid in mids:
                dissent = self.mode in {"dissent", "false_consensus", "unresolved", "missing_response"} \
                    and agent == "evaluator:effectiveness"
                if self.mode == "revise" and payload["round"] == 1 and agent == "evaluator:effectiveness":
                    dissent = True
                responses.append({"metric_id": mid, "decision": "disagree" if dissent else "agree",
                    "reason": "请核对原文与锚点。" if dissent else "核对所引原文后接受当前报告及分数。",
                    "evidence_ids": ["e-m1"], "issue_type": "anchor" if dissent else "none",
                    "revised_finding": finding(mid, 3) if self.mode == "revise" and dissent else None})
            return {"report_version": payload["report_version"], "feedback": responses}
        items = []
        for mid in mids:
            spec = payload["frozen_skills"][mid]
            blockers = spec.get("scoring_blockers", [])
            f = finding(mid, 3 if self.mode == "revise" and purpose != "leader_preliminary" else 4)
            if blockers:
                f = finding(mid, None, status="NOT_EVALUABLE", claims=[], evidence_ids=[], review_rule_ids=blockers)
            if self.mode == "unresolved" and purpose == "leader_final":
                f = finding(mid, None, status="NOT_EVALUABLE", claims=[], evidence_ids=[],
                            review_rule_ids=["source_incomplete"], reason="缺少影响判断的原文。")
            feedback = payload["received_feedback"][mid]
            if self.mode == "missing_response" and purpose == "leader_final":
                feedback = feedback[:2]
            responses = [{"feedback_id": fb["feedback_id"],
                          "disposition": "accepted" if fb["decision"] == "agree" or self.mode == "revise" else "rejected",
                          "reason": "核对当前原文并按锚点说明采纳或维持判断。", "evidence_ids": ["e-m1"]}
                         for fb in feedback]
            method = "provisional"
            if purpose == "leader_final":
                method = "consensus" if self.mode == "false_consensus" else "evidence_adjudicated"
                if self.mode == "unresolved":
                    method = "not_evaluable"
            items.append({"finding": f, "question": "请逐条定位患者诉求与医生回应，核对本项锚点。",
                          "factual_resolution": "unresolved" if self.mode == "unresolved" and purpose == "leader_final" else "resolved",
                          "decision_method": method, "responses": responses})
        return {"report_version": payload["report_version"], "items": items}


def test_projection_enforces_normalized_bounds_even_for_extreme_candidates():
    rng = random.Random(42)
    for size in range(1, 19):
        for _ in range(20):
            original = {str(i): rng.random() ** 12 for i in range(size)}
            result = bounded_weights(original)
            assert math.isclose(sum(result.values()), 1, abs_tol=1e-12)
            assert all(.8 / size - 1e-12 <= w <= 1.2 / size + 1e-12 for w in result.values())
            assert original != result or size == 1
    assert bounded_weights({"a": 999, "b": 1}) == pytest.approx({"a": .6, "b": .4})
    assert bounded_weights({"a": 999, "b": 1}, 0) == {"a": .5, "b": .5}
    assert bounded_weights({"a": 1e308, "b": 1e308}) == pytest.approx({"a": .5, "b": .5})
    for bad in ({"a": float("nan")}, {"a": -1}, {"a": 0}, {"a": float("inf")}):
        with pytest.raises(ValueError):
            bounded_weights(bad)


async def test_default_protocol_selected_only_and_private_initials(make_service, session):
    model = ProtocolModel(selected=["D1.1"])
    service, repo = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["quality_profile"]["overall_score"] == 4
    assert report["quality_profile"]["required_count"] == 1
    assert len(report["agent_results"]) == 1  # canonical Leader result, not last-writer teammate overwrite
    assert report["collaboration"]["round_count"] == 1
    assert report["collaboration"]["weights"] == {"D1.1": 1}
    assert len(report["collaboration"]["initial_evaluations"]) == 3
    assert all(len(a["findings"]) == 1 for a in report["collaboration"]["initial_evaluations"])
    for p in model.payloads:
        if p["purpose"] == "initial_evaluation":
            assert "current_report" not in p and "initial_evaluations" not in p
            assert p["requested_metric_ids"] == ["D1.1"]
    state = await repo.get_run(report["evaluation_id"])
    assert all(m["status"] == "PROCESSED" for m in state["team"]["messages"])
    assert all("team_lead" in {m["sender"], m["receiver"]} for m in state["team"]["messages"])
    assert state["team"]["final_findings"]["D1.1"]["decision_method"] == "consensus"
    assert await service.execute(report["evaluation_id"]) == report


async def test_three_rounds_then_evidence_adjudication_preserves_dissent(make_service, session):
    model = ProtocolModel("dissent")
    service, repo = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["quality_profile"]["overall_score"] == 4
    assert report["collaboration"]["round_count"] == 3
    assert {p["round"] for p in model.payloads if p["purpose"].startswith("evaluator_feedback_")} == {1, 2, 3}
    assert report["agent_results"][0]["findings"][0]["decision_method"] == "evidence_adjudicated"
    assert report["arbitration_status"] == "resolved"
    assert len(report["arbitration_decisions"]) == 2
    assert "不代表全体一致" in report["summary"]
    assert any(f["decision"] == "disagree" for f in report["collaboration"]["feedback"])
    final = report["collaboration"]["reports"][-1]
    assert final["final"]
    assert all(len(item["responses"]) == 3 for item in final["findings"])
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["initial_evaluations"]["evaluator:effectiveness"]["D1.1"]["score"] == 1
    assert state["team"]["score_gaps"]["D1.1"]["large_gap"]
    weights = report["collaboration"]["weights"]
    assert all(p["weights"] == weights for p in model.payloads if p["purpose"] != "leader_plan")


async def test_leader_accepts_reasonable_objection_and_new_version_is_reviewed(make_service, session):
    model = ProtocolModel("revise")
    service, _ = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["collaboration"]["round_count"] == 2
    assert report["quality_profile"]["overall_score"] == 3
    assert [r["version"] for r in report["collaboration"]["reports"]] == [0, 1]
    assert all(f["decision_method"] == "consensus" for f in report["agent_results"][0]["findings"])
    assert any(f["report_version"] == 1 for f in report["collaboration"]["feedback"])


@pytest.mark.parametrize("mode", ["false_consensus", "missing_response"])
async def test_false_consensus_or_unanswered_objections_are_rejected(make_service, session, mode):
    service, repo = await make_service(ProtocolModel(mode), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["quality_profile"]["overall_score"] is None
    assert not report["collaboration_complete"]
    state = await repo.get_run(report["evaluation_id"])
    assert any(e["action"] == "submission_rejected" for e in state["team"]["events"])


async def test_unresolved_source_not_forced_into_adjudicated_number(make_service, session):
    service, _ = await make_service(ProtocolModel("unresolved"), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["collaboration_complete"]
    assert report["quality_profile"]["overall_score"] is None
    assert all(f["outcome"] == "insufficient_evidence" for f in report["agent_results"][0]["findings"])


async def test_partial_initial_submission_preserves_valid_sibling(make_service, session):
    model = ProtocolModel("partial")
    service, repo = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    state = await repo.get_run(report["evaluation_id"])
    assert any(e["action"] == "submission_rejected" for e in state["team"]["events"])
    calls = [p for p in model.payloads if p["purpose"] == "initial_evaluation"
             and p["task"]["assigned_agent"] == "evaluator:effectiveness"]
    assert len(calls[0]["requested_metric_ids"]) == 2
    assert len(calls[1]["requested_metric_ids"]) == 1
    errors = [e for e in state["team"]["events"] if e["action"] == "submission_rejected"]
    assert any("unknown" in e["detail"]["error"] and "e-m1" in e["detail"]["error"] for e in errors)


async def test_incomplete_retry_keeps_plan_weights_and_completed_initials(make_service, session):
    service, repo = await make_service(ProtocolModel("timeout"), team_protocol=PROTOCOL)
    first = await service.evaluate(session)
    assert first["status"] == "failed"
    old = copy.deepcopy(await repo.get_run(first["evaluation_id"]))
    new_id = await service.retry_incomplete(first["evaluation_id"])
    service.model = ProtocolModel()
    second = await service.execute(new_id)
    assert second["status"] == "completed"
    assert second["collaboration"]["weights"] == first["collaboration"]["weights"]
    assert not any(p["purpose"] == "leader_plan" for p in service.model.payloads)
    assert all(p["task"]["assigned_agent"] == "evaluator:empathy"
               for p in service.model.payloads if p["purpose"] == "initial_evaluation")
    assert (await repo.get_run(first["evaluation_id"]))["report"] == old["report"]


async def test_full_production_catalog_batches_and_d2_exclusions(make_service, session):
    model = ProtocolModel()
    service, _ = await make_service(model, team_protocol=PROTOCOL)
    service.catalog = SkillCatalog(Settings().skill_dir)
    service.knowledge = SkillKnowledgeSource(service.catalog)
    # Initial evaluator must also obey the production blockers.
    original = model.json
    async def actual(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"] == "initial_evaluation":
            for f in result["findings"]:
                rules = payload["frozen_skills"][f["metric_id"]].get("scoring_blockers", [])
                if rules:
                    f.update(status="NOT_EVALUABLE", score=None, claims=[], evidence_ids=[], review_rule_ids=rules)
        return result
    model.json = actual
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["quality_profile"]["evaluated_count"] == 16
    assert report["quality_profile"]["overall_score"] == 4
    assert sum(len(a["findings"]) for a in report["collaboration"]["initial_evaluations"]) == 54
    assert all(.8 / 16 - 1e-12 <= w <= 1.2 / 16 + 1e-12 for w in report["quality_profile"]["weights"].values())


async def test_checkpoint_resume_does_not_duplicate_committed_messages(make_service, session):
    service, repo = await make_service(ProtocolModel(), team_protocol=PROTOCOL)
    new_id = await service.create(session)
    original = repo.checkpoint
    interrupted = False
    async def checkpoint(data, owner):
        nonlocal interrupted
        await original(data, owner)
        if data.get("team", {}).get("reports") and not interrupted:
            interrupted = True
            raise asyncio.CancelledError
    repo.checkpoint = checkpoint
    with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
        await service.execute(new_id)
    repo.checkpoint = original
    report = await service.execute(new_id)
    assert report["status"] == "completed"
    state = await repo.get_run(new_id)
    ids = [m["message_id"] for m in state["team"]["messages"]]
    assert len(ids) == len(set(ids))


async def test_empty_selection_and_missing_model_do_not_invent_metrics(make_service, session):
    service, _ = await make_service(ProtocolModel(selected=[]), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["collaboration"]["selected_metric_ids"] == []
    assert report["quality_profile"]["overall_score"] is None
    model = ProtocolModel()
    model.configured = False
    service, _ = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "failed"
    assert not model.payloads
    assert report["quality_profile"]["selected_metric_ids"] == []


async def test_messagebus_rejects_peer_to_peer(make_service, session):
    service, repo = await make_service(ProtocolModel(), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    with pytest.raises(ValueError, match="Leader"):
        MessageBus(state["team"], 60).send_message("evaluator:effectiveness", "evaluator:empathy", "QUESTION", {})


async def test_evaluator_can_be_persuaded_by_report_and_gaps_follow_current_acceptance(make_service, session):
    service, repo = await make_service(ProtocolModel("persuaded"), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["initial_score_gaps"]["D1.1"]["gap"] == 3
    assert state["team"]["score_gaps"]["D1.1"]["gap"] == 0
    assert state["team"]["initial_evaluations"]["evaluator:effectiveness"]["D1.1"]["score"] == 1
    assert state["team"]["final_findings"]["D1.1"]["score"] == 4


async def test_no_model_calls_after_budget_and_no_fabricated_final(make_service, session):
    model = ProtocolModel()
    service, _ = await make_service(model, team_protocol=PROTOCOL, max_model_calls=1)
    report = await service.evaluate(session)
    assert len(model.payloads) == 1
    assert report["team"]["stop_reason"] == "model_call_budget_exhausted"
    assert report["quality_profile"]["overall_score"] is None
    assert all(f["outcome"] == "execution_failed" for f in report["agent_results"][0]["findings"])


async def test_excluded_final_metric_renormalizes_remaining_without_score_bias(make_service, session):
    model = ProtocolModel()
    original = model.json
    async def adapted(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"] == "leader_preliminary":
            for item in result["items"]:
                if item["finding"]["metric_id"] == "D1.1":
                    item["finding"] = finding("D1.1", None, status="NOT_APPLICABLE", claims=[], evidence_ids=[])
        return result
    model.json = adapted
    service, _ = await make_service(model, team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["quality_profile"]["required_count"] == 1
    assert report["quality_profile"]["weights"] == {"D2.1": 1}
    assert report["quality_profile"]["overall_score"] == 4
    assert report["collaboration"]["weights"] == pytest.approx({"D1.1": .6, "D2.1": .4})


async def test_total_timeout_is_not_reported_as_missing_source(make_service, session):
    class Slow(ProtocolModel):
        async def json(self, *args):
            await asyncio.sleep(2)
    service, _ = await make_service(Slow(), team_protocol=PROTOCOL, total_timeout=.15)
    report = await service.evaluate(session)
    assert report["team"]["stop_reason"] == "total_timeout"
    assert report["quality_profile"]["overall_score"] is None
    assert not report["collaboration_complete"]
