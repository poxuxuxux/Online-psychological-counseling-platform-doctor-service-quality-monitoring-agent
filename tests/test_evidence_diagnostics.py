# 环节：真实模型失败回归；用途：防止猜测证据ID、无法修正的拒收反馈和访客诊断丢失。
import pytest

from app.team.lead_protocol import PROTOCOL, LeaderProtocol, initialize_protocol
from app.team.tools import TeamTools
from tests.test_leader_protocol import ProtocolModel


def test_invalid_evidence_is_still_rejected_with_registered_ids_in_error():
    team = {"evidence": {"e-real": {"message_id": "real"}}}
    with pytest.raises(ValueError, match="Unknown evidence reference") as error:
        TeamTools.check_evidence(team, ["made-up"])
    assert "made-up" in str(error.value)
    assert "e-real" in str(error.value)
    assert "copy dialogue.messages[].evidence_id exactly" in str(error.value)
    TeamTools.check_evidence(team, ["e-real"])


async def test_preloaded_exact_id_is_next_to_message_and_unsupported_message_has_none(make_service, session):
    from app.context.service import preprocess
    service, _ = await make_service(ProtocolModel(), team_protocol=PROTOCOL)
    data = {"run_id": "test", "session": preprocess(session), "context": {},
            "skills": service.catalog.snapshot(), "team_plan": {"weights": {}},
            "team": initialize_protocol(service.catalog.snapshot(), "test")}
    data["team"]["evidence"] = {"e-m1": {"message_id": "m1"}}
    protocol = LeaderProtocol(service.settings, service.model, None, None)
    payload = protocol._base(data, "evaluator:effectiveness", "initial_evaluation", ["D1.1"])
    assert payload["dialogue"]["messages"][0]["evidence_id"] is None
    assert payload["dialogue"]["messages"][1]["evidence_id"] == "e-m1"
    assert "evidence_id" not in data["session"]["messages"][1]  # Original immutable input stays intact.


async def test_failure_report_keeps_field_diagnostics_without_model_inputs(make_service, session):
    class InvalidPlan(ProtocolModel):
        async def json(self, *args):
            return {"selected": []}
    service, _ = await make_service(InvalidPlan(), team_protocol=PROTOCOL)
    report = await service.evaluate(session)
    assert report["status"] == "failed"
    issue = report["execution_issues"][-1]
    assert issue["stage"] == "leader_plan"
    assert issue["metric_id"] == "plan"
    assert issue["attempt"] == 3
    assert any(f["path"] == ["context_summary"] and f["type"] == "missing" for f in issue["fields"])
    assert all("input" not in field for field in issue["fields"])
