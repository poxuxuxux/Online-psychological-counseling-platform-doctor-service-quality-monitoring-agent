"""Nonfinal status and final adjudication method are distinct contracts."""
import copy

import pytest

from app.config import Settings
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.team.post_initial_protocol import PROTOCOL_V2
from app.team.protocol_models import LeaderBatch, leader_batch_schema
from tests.test_post_initial import PostInitialModel


def test_phase_schema_isolated_from_shared_model_and_final_schema():
    original = copy.deepcopy(LeaderBatch.model_json_schema())
    provisional = leader_batch_schema(final=False)
    final = leader_batch_schema(final=True)
    method = provisional["$defs"]["LeaderItem"]["properties"]["decision_method"]
    assert method["const"] == "provisional"
    assert method["enum"] == ["provisional"]
    final_method = final["$defs"]["LeaderItem"]["properties"]["decision_method"]
    assert "provisional" not in final_method["enum"]
    assert "const" not in final_method
    assert LeaderBatch.model_json_schema() == original


@pytest.mark.parametrize("recover", [True, False])
async def test_timing_blocker_in_p0_requires_provisional_then_can_recover(make_service, session, recover):
    model = PostInitialModel(selected=["D1.1", "D2.1"])
    original = model.json
    attempts = []

    async def mismatched(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"] == "leader_preliminary" and "D2.1" in payload["requested_metric_ids"]:
            attempts.append(copy.deepcopy(payload))
            blocked = next(i for i in result["items"] if i["finding"]["metric_id"] == "D2.1")
            assert blocked["finding"]["status"] == "NOT_EVALUABLE"
            assert blocked["finding"]["score"] is None
            if not recover or len(attempts) == 1:
                blocked["decision_method"] = "not_evaluable"
        return result

    model.json = mismatched
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    service.catalog = SkillCatalog(Settings().skill_dir)
    service.knowledge = SkillKnowledgeSource(service.catalog)
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    assert "expected decision_method='provisional'" in attempts[1]["last_errors"]["D2.1"]["error"]
    if recover:
        assert report["status"] == "completed"
        item = state["team"]["reports"][0]["items"]["D2.1"]
        assert item["decision_method"] == "provisional"
        assert item["finding"]["status"] == "NOT_EVALUABLE"
        assert item["finding"]["score"] is None
        assert len(attempts) == 2
        assert attempts[1]["requested_metric_ids"] == ["D2.1"]
    else:
        assert report["team"]["stop_reason"] == "metric_submission_rejected"
        assert state["team"]["reports"] == []
        assert report["quality_profile"]["overall_score"] is None
        assert len(attempts) == 3
