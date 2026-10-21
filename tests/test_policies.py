# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
import json
from dataclasses import replace

import pytest

from app.config import Settings
from app.evaluation.scoring import classify_risk
from app.infrastructure.model import JsonModelGateway, ModelUnavailable
from app.rubrics.catalog import SkillCatalog
from app.team.conflicts import detect_fact_conflicts
from app.team.state import initialize_team
from app.team.tools import TeamTools


def test_real_skills_keep_unapproved_d6_metrics_draft():
    catalog = SkillCatalog(Settings().skill_dir)
    assert len(catalog.metrics) == 18
    assert len(catalog.dimensions) == 6
    assert {mid for mid, m in catalog.metrics.items() if m["status"] == "draft"} == {
        "D6.1", "D6.2"
    }
    assert not any(m["configuration_issues"] for m in catalog.metrics.values())


@pytest.mark.parametrize("metric_id", ["D6.1", "D6.2"])
def test_d6_draft_scoring_requires_manual_review(metric_id):
    catalog = SkillCatalog(Settings().skill_dir)
    state = {"skills": catalog.snapshot(), "team": initialize_team(catalog.snapshot(), "run")}
    agent = "evaluator:D4"
    state["team"]["tasks"][agent]["skills_read"] = True
    state["team"]["evidence"]["e1"] = {"evidence_id": "e1"}
    tools = TeamTools(Settings(), None)
    finding = {
        "metric_id": metric_id, "status": "EVALUATED", "score": 3,
        "reason": "Observed response", "evidence_ids": ["e1"],
        "claims": [{"subject": "doctor", "behavior": "respond", "polarity": "present",
                    "scope": "current_session", "statement": "Doctor replied", "evidence_ids": ["e1"]}],
        "review_rule_ids": [],
    }
    with pytest.raises(ValueError, match="not published"):
        tools.submit(state, agent, {"findings": [finding]})
    finding.update(status="NOT_EVALUABLE", score=None)
    with pytest.raises(ValueError, match="rubric_unpublished"):
        tools.submit(state, agent, {"findings": [finding]})
    finding["review_rule_ids"] = ["rubric_unpublished", "professional_protocol_pending"]
    assert tools.submit(state, agent, {"findings": [finding]})["accepted"] == [metric_id]


def test_d2_interaction_time_does_not_require_first_response_start():
    catalog = SkillCatalog(Settings().skill_dir)
    state = {"skills": catalog.snapshot(), "team": initialize_team(catalog.snapshot(), "run")}
    agent = "evaluator:D2"
    current = state["team"]["tasks"][agent]
    current["skills_read"] = True
    current["time_facts"] = TeamTools.time_facts({
        "service_context": {},
        "messages": [
            {"message_id": "p1", "role": "patient", "message_kind": "dialogue",
             "modality": "text", "content": "Question", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"message_id": "d1", "role": "doctor", "message_kind": "dialogue",
             "modality": "text", "content": "Answer", "timestamp": "2026-01-01T00:03:00+00:00"},
        ],
    })
    assert not current["time_facts"]["first_response_available"]
    assert current["time_facts"]["adjacent_response_available"]
    state["team"]["evidence"]["e1"] = {"evidence_id": "e1"}
    tools = TeamTools(Settings(), None)
    finding = {
        "metric_id": "D2.2", "status": "EVALUATED", "score": 4,
        "reason": "Three minute interaction", "evidence_ids": ["e1"],
        "claims": [{"subject": "doctor", "behavior": "respond", "polarity": "present",
                    "scope": "current_session", "statement": "Doctor replied", "evidence_ids": ["e1"]}],
        "review_rule_ids": [],
    }
    assert tools.submit(state, agent, {"findings": [finding]})["accepted"] == ["D2.2"]
    finding["metric_id"] = "D2.1"
    with pytest.raises(ValueError, match="first-response"):
        tools.submit(state, agent, {"findings": [finding]})


def test_new_dimension_requires_no_runtime_code_change(catalog):
    snapshot = catalog.snapshot()
    snapshot["metrics"]["D99.1"] = {**snapshot["metrics"]["D1.1"], "dimension_id": "D99"}
    team = initialize_team(snapshot, "run")
    assert "evaluator:D99" in team["tasks"]
    assert team["tasks"]["evaluator:D99"]["metric_ids"] == ["D99.1"]


def test_standard_dimensions_are_assigned_to_three_evaluator_groups():
    catalog = SkillCatalog(Settings().skill_dir)
    team = initialize_team(catalog.snapshot(), "run")
    assert set(team["tasks"]) == {"evaluator:D1", "evaluator:D2", "evaluator:D4"}
    assert team["tasks"]["evaluator:D1"]["dimension_ids"] == ["D1", "D3"]
    assert team["tasks"]["evaluator:D2"]["dimension_ids"] == ["D2", "D5"]
    assert team["tasks"]["evaluator:D4"]["dimension_ids"] == ["D4", "D6"]
    assert team["tasks"]["evaluator:D1"]["metric_ids"] == [
        "D1.1", "D1.2", "D3.1", "D3.2", "D3.3", "D3.4", "D3.5"
    ]


def test_different_scores_are_not_fact_conflicts(catalog):
    team = initialize_team(catalog.snapshot(), "run")
    for index, (agent, task) in enumerate(team["tasks"].items()):
        mid = task["metric_ids"][0]
        task["findings"][mid] = {"metric_id": mid, "score": index + 1, "claims": []}
    detect_fact_conflicts(team)
    assert not team["conflicts"]


async def test_serious_alert_is_sticky_and_budget_bounded(catalog):
    team = initialize_team(catalog.snapshot(), "run")
    team["evidence"]["e1"] = {"evidence_id": "e1"}
    state = {
        "run_id": "run",
        "team": team,
        "skills": catalog.snapshot(),
        "checks": {},
        "quality_profile": {"overall_score": 5},
    }
    tools = TeamTools(replace(Settings(), max_messages=1), None)
    args = {
        "receiver": "evaluator:D2",
        "message_type": "RISK_ALERT",
        "content": "Serious service concern",
        "evidence_ids": ["e1"],
    }
    tools.send(state, "evaluator:D1", args)
    assert classify_risk(state)["level"] == "high"
    with pytest.raises(ValueError, match="budget"):
        tools.send(state, "evaluator:D1", args)
    assert classify_risk(state)["level"] == "high"


async def test_model_http_transport_no_hidden_retry(monkeypatch):
    import httpx

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, json={"private_error": "must not propagate"})

    model = JsonModelGateway(httpx.MockTransport(respond))
    with pytest.raises(ModelUnavailable, match="^model_http_429$"):
        await model.json("test", {}, {})
    assert len(calls) == 1


async def test_deepseek_provider_detection_and_reasoner_format(monkeypatch):
    import httpx

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("GLM_API_KEY", "also-present-but-lower-priority")
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "{\"ok\":1}"}}]},
        )

    model = JsonModelGateway(httpx.MockTransport(respond))
    assert model.provider == "deepseek"
    assert model.base_url == "https://api.deepseek.com/v1"
    assert model.key == "test-key"
    await model.json("test", {}, {})
    assert bodies[0]["response_format"] == {"type": "json_object"}

    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    reasoner = JsonModelGateway(httpx.MockTransport(respond))
    await reasoner.json("test", {}, {})
    assert "response_format" not in bodies[1]


def test_production_requires_railway_postgres(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValueError, match="Railway PostgreSQL"):
        Settings.from_env()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/local/private.sqlite3")
    with pytest.raises(ValueError, match="Railway PostgreSQL"):
        Settings.from_env()
    monkeypatch.setenv("DATABASE_URL", "postgresql://railway.example/db")
    assert Settings.from_env().seed_demo is False
