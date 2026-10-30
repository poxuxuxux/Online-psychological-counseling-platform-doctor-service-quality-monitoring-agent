# 环节：三阶段协议回归；用途：验证初评在先、Leader自主选项、归一化平均且无等权限幅。
import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.team.post_initial_protocol import PROTOCOL_V2
from app.team.weights import average_stage_weights, normalize_weights
from tests.test_leader_protocol import ProtocolModel


class PostInitialModel(ProtocolModel):
    def __init__(self, selected=None, stage_vectors=None):
        super().__init__(selected=selected)
        self.stage_vectors = stage_vectors

    async def json(self, system, payload, schema):
        purpose = payload["purpose"]
        if purpose.startswith("leader_weight_"):
            self.payloads.append(copy.deepcopy(payload))
            stage = purpose.removeprefix("leader_weight_")
            mids = payload["requested_metric_ids"]
            chosen = mids[:1] if self.selected is None else self.selected
            vector = (self.stage_vectors[stage] if self.stage_vectors is not None
                      else {mid: 1 for mid in chosen})
            return {"context_summary": "本次情境", "task_analysis": "根据本次任务选择",
                    "relevance_analysis": "患者核心需求", "consistency_check": "不依赖同伴的适用性白名单",
                    "selected": [{"metric_id": mid, "candidate_weight": w, "reason": "Leader核对原文后保留"}
                                 for mid, w in vector.items()],
                    "excluded": [{"metric_id": mid, "reason": "Leader决定不保留"} for mid in mids if mid not in vector]}
        result = await super().json(system, payload, schema)
        if purpose == "initial_evaluation":
            assert "weights" not in payload
            for f in result["findings"]:
                blockers = payload["frozen_skills"][f["metric_id"]].get("scoring_blockers", [])
                if blockers:
                    f.update(status="NOT_EVALUABLE", score=None, evidence_ids=[], claims=[], review_rule_ids=blockers)
                if f["metric_id"] == "D4.1":
                    f.update(status="NOT_APPLICABLE", score=None, evidence_ids=[], claims=[])
        return result


def test_stage_normalization_mean_zero_fill_and_no_clipping():
    result = average_stage_weights([{"A": 7, "C": 2, "D": 1},
                                    {"A": 6, "C": 2, "D": 1, "B": 1}, {"A": 8, "D": 2}])
    assert result == pytest.approx({"A": .7, "B": 1/30, "C": 2/15, "D": 2/15})
    assert result["A"] > .3  # Not projected to the old four-metric 20%-30% range.
    assert normalize_weights({"A": 7, "B": 1}) == pytest.approx({"A": .875, "B": .125})
    assert average_stage_weights([{}, {}, {}]) == {}
    for invalid in ([{"A": 1}, {}, {"A": 1}], [{"A": 0}] * 3, [{"A": -1}] * 3):
        with pytest.raises(ValueError):
            average_stage_weights(invalid)


async def test_entire_initial_precedes_stages_and_leader_drops_scored_items(make_service, session):
    model = PostInitialModel(selected=["D1.1"])
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    collab = report["collaboration"]
    assert collab["selected_metric_ids"] == ["D1.1"]
    assert all(len(a["findings"]) == 2 for a in collab["initial_evaluations"])
    assert report["quality_profile"]["required_count"] == 1
    purposes = [p["purpose"] for p in model.payloads]
    assert max(i for i, purpose in enumerate(purposes) if purpose == "initial_evaluation") < purposes.index("leader_weight_scenario")
    assert purposes.index("leader_weight_relevance") < purposes.index("leader_preliminary")
    scenario = next(p for p in model.payloads if p["purpose"] == "leader_weight_scenario")
    distribution = next(p for p in model.payloads if p["purpose"] == "leader_weight_distribution")
    assert "initial_evaluations" not in scenario
    assert len(distribution["initial_evaluations"]) == 3
    assert len(collab["weighting_stages"]) == 3
    assert collab["weight_deviation"] is None
    assert report["quality_profile"]["weights"] == {"D1.1": 1}
    state = await repo.get_run(report["evaluation_id"])
    assert all(m["status"] == "PROCESSED" for m in state["team"]["messages"])


async def test_all_18_initials_and_leader_keeps_peer_not_applicable_metric(make_service, session):
    model = PostInitialModel(selected=["D1.1", "D4.1"])
    service, _ = await make_service(model, team_protocol=PROTOCOL_V2)
    service.catalog = SkillCatalog(Settings().skill_dir)
    service.knowledge = SkillKnowledgeSource(service.catalog)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    collab = report["collaboration"]
    assert sum(len(a["findings"]) for a in collab["initial_evaluations"]) == 54
    assert all(next(f for f in a["findings"] if f["metric_id"] == "D4.1")["status"] == "NOT_APPLICABLE"
               for a in collab["initial_evaluations"])
    assert "D4.1" in collab["selected_metric_ids"]
    assert report["quality_profile"]["required_count"] == 2
    assert all(f["score"] == 4 for f in report["agent_results"][0]["findings"])
    assert any("D4.1" in p["requested_metric_ids"] for p in model.payloads if p["purpose"].startswith("evaluator_feedback_"))


async def test_missing_stage_does_not_silently_divide_by_two(make_service, session):
    model = PostInitialModel(stage_vectors={"scenario": {"D1.1": 1}, "distribution": {}, "relevance": {"D1.1": 1}})
    service, _ = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    assert report["status"] == "failed"
    assert report["team"]["stop_reason"] == "weight_stage_incomplete"
    assert report["quality_profile"]["overall_score"] is None
    assert len(report["collaboration"]["weighting_stages"]) == 3


async def test_v2_ignores_legacy_weight_deviation(make_service, session):
    vectors = {"scenario": {"D1.1": 99, "D2.1": 1}, "distribution": {"D1.1": 99, "D2.1": 1},
               "relevance": {"D1.1": 99, "D2.1": 1}}
    service, _ = await make_service(PostInitialModel(stage_vectors=vectors), team_protocol=PROTOCOL_V2, weight_deviation=0)
    report = await service.evaluate(session)
    assert report["collaboration"]["weights"] == pytest.approx({"D1.1": .99, "D2.1": .01})
    assert report["quality_profile"]["weights"] == pytest.approx({"D1.1": .99, "D2.1": .01})


def test_default_guest_api_uses_initial_first_protocol(tmp_path, catalog, session):
    settings = replace(Settings(), seed_demo=False, database_url="sqlite:///" + str(tmp_path / "host.sqlite3"))
    assert settings.team_protocol == PROTOCOL_V2
    with TestClient(create_app(settings, model=PostInitialModel(), catalog=catalog)) as client:
        response = client.post('/api/v1/guest/evaluations', json=session.model_dump(mode='json'))
        assert response.status_code == 200, response.text
        assert response.json()['collaboration']['protocol'] == PROTOCOL_V2
        assert len(response.json()['collaboration']['weighting_stages']) == 3
        assert client.get('/ready').json()['team']['weight_deviation'] is None


async def test_real_catalog_picture_example_matches_exact_average(make_service, session):
    vectors = {"scenario": {"D1.1": 7, "D3.4": 2, "D5.4": 1},
               "distribution": {"D1.1": 6, "D3.4": 2, "D5.4": 1, "D4.1": 1},
               "relevance": {"D1.1": 8, "D5.4": 2}}
    service, _ = await make_service(PostInitialModel(stage_vectors=vectors), team_protocol=PROTOCOL_V2)
    service.catalog = SkillCatalog(Settings().skill_dir)
    service.knowledge = SkillKnowledgeSource(service.catalog)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["collaboration"]["weights"] == pytest.approx({"D1.1": .7, "D3.4": 2/15, "D5.4": 2/15, "D4.1": 1/30})
    assert report["quality_profile"]["weights"] == pytest.approx(report["collaboration"]["weights"])


async def test_stage_checkpoint_resume_does_not_repeat_initials_or_completed_stage(make_service, session):
    import asyncio

    from langgraph.errors import NodeCancelledError
    model = PostInitialModel()
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    run_id = await service.create(session)
    checkpoint = repo.checkpoint
    interrupted = False
    async def crash(data, owner):
        nonlocal interrupted
        await checkpoint(data, owner)
        if data.get("team", {}).get("weighting_stages", {}).get("scenario") and not interrupted:
            interrupted = True
            raise asyncio.CancelledError
    repo.checkpoint = crash
    with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
        await service.execute(run_id)
    repo.checkpoint = checkpoint
    model.payloads.clear()
    report = await service.execute(run_id)
    assert report["status"] == "completed"
    assert not any(p["purpose"] in {"initial_evaluation", "leader_weight_scenario"} for p in model.payloads)
