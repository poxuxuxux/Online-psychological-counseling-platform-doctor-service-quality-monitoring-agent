# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
import json
from dataclasses import replace

import pytest

from app.config import Settings
from app.evaluation.scoring import classify_risk, score
from app.infrastructure.model import JsonModelGateway, ModelUnavailable, _decode_object
from app.rubrics.catalog import SkillCatalog
from app.rubrics.payload import metric_payload
from app.team.state import initialize_team
from app.team.tools import TeamTools


def test_real_skills_publish_catalog_from_skill_frontmatter():
    catalog = SkillCatalog(Settings().skill_dir)
    assert len(catalog.metrics) == 18
    assert len(catalog.dimensions) == 6
    assert all(m["status"] == "published" for m in catalog.metrics.values())
    assert all("scoring_status" not in m for m in catalog.metrics.values())
    assert not any(m["configuration_issues"] for m in catalog.metrics.values())
    assert all(not (Settings().skill_dir / mid / "metric.yaml").exists() for mid in catalog.metrics)
    assert "风险信号回应" in metric_payload(catalog.metrics["D6.1"])["instructions"]


def test_nonapplicable_d6_allows_total_but_applicable_pending_d6_blocks_it():
    catalog = SkillCatalog(Settings().skill_dir)
    skills = catalog.snapshot()
    team = initialize_team(skills, "run")
    team["evidence"]["e1"] = {"evidence_id": "e1"}
    for task in team["tasks"].values():
        for mid in task["metric_ids"]:
            task["findings"][mid] = {
                "metric_id": mid,
                "status": "NOT_APPLICABLE" if mid.startswith("D6.") else "EVALUATED",
                "score": None if mid.startswith("D6.") else 4,
                "review_rule_ids": [], "evidence_ids": ["e1"], "claims": [{"evidence_ids": ["e1"]}],
            }
    state = {"skills": skills, "team": team, "dimension_ids": catalog.dimensions,
             "completion": {"complete": True}}
    assert score(state)["overall_score"] == 4
    team["tasks"]["evaluator:D4"]["findings"]["D6.1"].update(
        status="NOT_EVALUABLE", review_rule_ids=["urgent_safety_review"]
    )
    assert score(state)["overall_score"] is None


@pytest.mark.parametrize("metric_id", ["D6.1", "D6.2"])
def test_published_d6_scores_clear_case_and_reviews_flagged_case(metric_id):
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
    assert tools.submit(state, agent, {"findings": [finding]})["accepted"] == [metric_id]
    finding["review_rule_ids"] = ["urgent_safety_review"]
    with pytest.raises(ValueError, match="Unresolved review rules"):
        tools.submit(state, agent, {"findings": [finding]})
    finding.update(status="NOT_EVALUABLE", score=None)
    assert tools.submit(state, agent, {"findings": [finding]})["accepted"] == [metric_id]


def test_d6_professional_review_distinguishes_absent_trigger_from_uncertain_trigger():
    catalog = SkillCatalog(Settings().skill_dir)
    state = {"skills": catalog.snapshot(), "team": initialize_team(catalog.snapshot(), "run")}
    agent = "evaluator:D4"
    state["team"]["tasks"][agent]["skills_read"] = True
    tools = TeamTools(Settings(), None)
    no_trigger = {"metric_id": "D6.1", "status": "NOT_APPLICABLE", "score": None,
                  "reason": "Complete dialogue contains no current safety concern",
                  "evidence_ids": [], "claims": [], "review_rule_ids": []}
    assert tools.submit(state, agent, {"findings": [no_trigger]})["accepted"] == ["D6.1"]
    no_trigger["review_rule_ids"] = ["rubric_unpublished"]
    with pytest.raises(ValueError, match="Unknown manual review rule"):
        tools.submit(state, agent, {"findings": [no_trigger]})
    uncertain = {**no_trigger, "status": "NOT_EVALUABLE",
                 "review_rule_ids": ["context_ambiguous"]}
    assert tools.submit(state, agent, {"findings": [uncertain]})["accepted"] == ["D6.1"]


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


def test_team_lead_owns_and_queues_conflict_arbitration():
    catalog = SkillCatalog(Settings().skill_dir)
    state = {"run_id": "run", "session": {}, "skills": catalog.snapshot(),
             "team": initialize_team(catalog.snapshot(), "run")}
    tools = TeamTools(Settings(), None)
    suggestion = tools.request_review(state, "evaluator:D1", {
        "metric_ids": ["D1.1", "D2.1"], "reason": "Conflicting source claims"
    })
    assert suggestion["status"] == "queued_for_team_lead"
    assert not state["team"]["conflicts"]
    lead = tools.ensure_team_lead(state)
    for task in state["team"]["tasks"].values():
        if task["kind"] == "evaluator":
            for mid in task["metric_ids"]:
                task["findings"][mid] = {"finding_id": "f-" + mid, "metric_id": mid, "claims": []}
    state["team"]["evidence"]["e1"] = {"evidence_id": "e1"}
    lead["skills_read"] = True
    assessment = tools.assess_conflicts(state, "team_lead", {
        "reason": "Checked source and identified two substantive conflicts",
        "conflicts": [
            {"metric_ids": ["D1.1", "D2.1"], "reason": "Opposite doctor behavior claims", "evidence_ids": ["e1"]},
            {"metric_ids": ["D4.1", "D6.1"], "reason": "Incompatible safety response claims", "evidence_ids": ["e1"]},
        ],
    })
    assert assessment["confirmed_conflicts"] == 2
    first, second = list(state["team"]["conflicts"])
    assert lead["conflict_id"] == first
    assert lead["pending_conflicts"] == [second]
    action = tools.execute(state, "team_lead", "submit_review", {
        "decision": "revise", "reason": "Original text favors one claim", "evidence_ids": ["e1"]
    })
    with pytest.raises(StopIteration) as completed:
        action.send(None)  # This tool path is synchronous; no event loop is needed.
    result = completed.value.value
    assert result["status"] == "arbitration_submitted"
    assert lead["conflict_id"] == second
    assert lead["status"] == "PENDING"
    assert state["team"]["conflicts"][first]["review"]["reviewer"] == "team_lead"


def test_team_lead_can_confirm_no_conflict_despite_different_scores(catalog):
    state = {"run_id": "run", "skills": catalog.snapshot(),
             "team": initialize_team(catalog.snapshot(), "run")}
    for index, task in enumerate(state["team"]["tasks"].values()):
        mid = task["metric_ids"][0]
        task["findings"][mid] = {"finding_id": "f-" + mid, "metric_id": mid,
                                 "score": index + 1, "claims": []}
    tools = TeamTools(Settings(), None)
    lead = tools.ensure_team_lead(state)
    result = tools.assess_conflicts(state, "team_lead", {
        "conflicts": [], "reason": "Scores differ across metrics, but factual claims do not conflict"
    })
    assert result["confirmed_conflicts"] == 0
    assert lead["status"] == "COMPLETED"
    assert not state["team"]["conflicts"]


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


def test_model_json_recovers_only_terminal_container_braces():
    assert _decode_object('{"score": 4}}') == ({"score": 4}, False, "extra_closing_brace")
    assert _decode_object('{"items": [{"score": 4}') == (
        {"items": [{"score": 4}]}, False, "missing_closing_brace"
    )
    with pytest.raises(json.JSONDecodeError):
        _decode_object('{"score": 4 "claim": "unsupported"}')


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
