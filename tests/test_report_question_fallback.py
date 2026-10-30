"""Missing discussion metadata must not discard a source-validated evaluation."""
import pytest

from app.team.post_initial_protocol import PROTOCOL_V2
from tests.test_post_initial import PostInitialModel


@pytest.mark.parametrize("question", ["", "  \n", None, "missing", "原文问题保留"])
async def test_empty_question_repaired_without_repeating_scoring(make_service, session, question):
    model = PostInitialModel(selected=["D1.1"])
    original = model.json

    async def blank(system, payload, schema):
        result = await original(system, payload, schema)
        if payload["purpose"] == "leader_preliminary":
            for item in result["items"]:
                if question == "missing":
                    item.pop("question")
                else:
                    item["question"] = question
        return result

    model.json = blank
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["quality_profile"]["overall_score"] == 4
    assert sum(p["purpose"] == "leader_preliminary" for p in model.payloads) == 1
    state = await repo.get_run(report["evaluation_id"])
    item = state["team"]["reports"][0]["items"]["D1.1"]
    repaired = question != "原文问题保留"
    assert item["question"].startswith("【程序补充】") if repaired else item["question"] == question
    events = [e for e in state["team"]["events"] if e["action"] == "report_question_defaulted"]
    assert len(events) == int(repaired)
    assert item["finding"]["score"] == 4
    assert item["finding"]["evidence_ids"] == ["e-m1"]


async def test_question_fallback_preserves_three_round_limit_and_big_gap(make_service, session):
    model = PostInitialModel(selected=["D1.1"])
    model.mode = "dissent"
    original = model.json

    async def blank(system, payload, schema):
        result = await original(system, payload, schema)
        if "items" in result:
            for item in result["items"]:
                item["question"] = ""
        return result

    model.json = blank
    service, repo = await make_service(model, team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert report["collaboration"]["round_count"] == 3
    state = await repo.get_run(report["evaluation_id"])
    assert "大分差" in state["team"]["reports"][0]["items"]["D1.1"]["question"]
    final = state["team"]["reports"][-1]["items"]["D1.1"]
    assert "不再开启新一轮" in final["question"]
    assert final["decision_method"] == "evidence_adjudicated"
