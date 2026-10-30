"""Workflow-owned versions are explicit and stale results cannot mutate reports."""
import copy

import pytest

from app.team.lead_protocol import PROTOCOL
from app.team.post_initial_protocol import PROTOCOL_V2
from app.team.protocol_models import FeedbackBatch, LeaderBatch
from tests.test_leader_protocol import ProtocolModel
from tests.test_post_initial import PostInitialModel


@pytest.mark.parametrize("protocol,model_type", [(PROTOCOL, ProtocolModel), (PROTOCOL_V2, PostInitialModel)])
@pytest.mark.parametrize("mode", ["revise", "dissent"])
async def test_every_report_and_feedback_request_binds_target_version(make_service, session, protocol, model_type, mode):
    model = model_type(selected=["D1.1"])
    model.mode = mode
    original = model.json
    versions = []
    schemas = [copy.deepcopy(m.model_json_schema()) for m in (LeaderBatch, FeedbackBatch)]

    async def checked(system, payload, schema):
        if "report_version" in payload:
            version = payload["report_version"]
            prop = schema["properties"]["report_version"]
            assert prop["const"] == version
            assert prop["enum"] == [version]
            assert f"report_version必须为整数{version}" in system
            versions.append(version)
            if payload["purpose"].startswith("leader_"):
                if payload.get("current_report"):
                    assert set(payload["current_report"]["items"]) == set(payload["requested_metric_ids"])
                methods = schema["$defs"]["LeaderItem"]["properties"]["decision_method"]
                if payload["report_is_final"]:
                    assert "provisional" not in methods["enum"]
                    assert "evidence_adjudicated" in methods["enum"]
                else:
                    assert methods["enum"] == ["provisional"]
                    assert methods["const"] == "provisional"
                    assert "decision_method必须且只能为provisional" in system
        return await original(system, payload, schema)

    model.json = checked
    service, _ = await make_service(model, team_protocol=protocol)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert 0 in versions and 1 in versions
    if mode == "dissent":
        assert set(versions) == {0, 1, 2, 3}
    assert schemas == [m.model_json_schema() for m in (LeaderBatch, FeedbackBatch)]


@pytest.mark.parametrize("protocol,model_type", [(PROTOCOL, ProtocolModel), (PROTOCOL_V2, PostInitialModel)])
@pytest.mark.parametrize("recover", [True, False])
async def test_wrong_preliminary_version_retries_without_silently_accepting(make_service, session, protocol, model_type, recover):
    model = model_type(selected=["D1.1"])
    original = model.json
    attempts = []

    async def shifted(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"] == "leader_preliminary":
            attempts.append(copy.deepcopy(payload))
            if not recover or len(attempts) == 1:
                result["report_version"] = 1
        return result

    model.json = shifted
    service, repo = await make_service(model, team_protocol=protocol)
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    assert all(p["report_version"] == 0 for p in attempts)
    assert "expected 0, received 1" in attempts[1]["last_errors"]["D1.1"]["error"]
    if recover:
        assert report["status"] == "completed"
        assert state["team"]["reports"][0]["version"] == 0
        assert len(attempts) == 2
    else:
        assert report["team"]["stop_reason"] == "metric_submission_rejected"
        assert state["team"]["reports"] == []
        assert all(f["decision_method"] == "execution_failed" and f["score"] is None
                   for f in state["team"]["final_findings"].values())
        assert report["quality_profile"]["overall_score"] is None
        assert len(attempts) == 3
