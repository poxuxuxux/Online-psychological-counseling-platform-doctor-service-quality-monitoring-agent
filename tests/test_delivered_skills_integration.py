"""Offline integration of the actual 18 delivered packages; no model API calls."""

import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.structured import StructuredEvaluation
from app.api.local_backend import create_app
from app.api.v1.evaluations import build_demo_session
from app.application.local_worker import run_one
from app.domain.models import Finding
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import snapshot
from app.skills.runtime import validate_finding
from tests.test_local_backend import FakeProvider

ROOT = Path(__file__).resolve().parents[1] / "app/skills/metric_packages"


class DeliveredProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.seen = {"evaluation": {}, "verification": {}}

    async def complete(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        result = json.loads(await super().complete(system_prompt, user_prompt))
        stage = "evaluation" if "metrics" in payload else "verification"
        definitions = payload.get("metrics", payload.get("definitions", []))
        for metric in definitions:
            self.seen[stage][metric["metric_id"]] = metric["skill"]["content_hash"]
        for finding in result.get("findings", []):
            finding.update(
                applicability="applicable", score=None,
                review_rule_ids=["rubric_unpublished"], requires_manual_review=True,
                limitations=["Synthetic integration fixture; not clinical validation"],
            )
        for check in result.get("checks", []):
            check.update(
                applicability_status="matched", rubric_status="uncertain",
                review_rule_ids=["rubric_unpublished"],
            )
        return json.dumps(result)


async def test_actual_packages_flow_through_worker_and_persisted_report(tmp_path):
    rubric = snapshot(ROOT)
    assert len(rubric["metrics"]) == 18
    assert Counter(m["owner"] for m in rubric["metrics"]) == {
        "professional_service": 8, "process_response": 6, "empathy_relationship": 4,
    }
    expected = {m["metric_id"]: m["skill"]["content_hash"] for m in rubric["metrics"]}
    session = build_demo_session()
    store = LocalJobStore(tmp_path / "integration.sqlite3")
    store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
    run_id = store.enqueue(session.session_id, "actual-skills", rubric)
    provider = DeliveredProvider()
    assert await run_one(store, StructuredEvaluation(provider, rubric))
    report = LocalJobStore(store.path).job(run_id)["report"]
    assert provider.seen == {"evaluation": expected, "verification": expected}
    assert report["rubric"] == rubric
    findings = [f for a in report["agent_results"] for f in a["findings"]]
    assert len(findings) == len(report["checks"]) == 18
    assert all(a["status"] == "completed" for a in report["agent_results"])
    assert all(f["score"] is None and f["requires_manual_review"] for f in findings)
    assert all("rubric_unpublished" in f["review_rule_ids"] for f in findings)
    assert report["overall_score"] is None
    assert report["summary_status"] == "skipped"
    versions = {m["metric_id"]: m["skill"]["spec"]["version"] for m in rubric["metrics"]}
    assert all(f["metric_version"] == versions[f["metric_id"]] for f in findings)


@pytest.mark.parametrize("metric", snapshot(ROOT)["metrics"], ids=lambda m: m["metric_id"])
def test_actual_draft_packages_reject_numeric_score(metric):
    with pytest.raises(ValueError, match="draft_skill_must_not_score"):
        validate_finding(metric, Finding(metric_id=metric["metric_id"], score=4, rationale="test"))


def test_api_discovers_installed_packages_and_queues_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("METRIC_SKILLS_DIR", str(ROOT))
    rubric = snapshot()
    store = LocalJobStore(tmp_path / "api.sqlite3")
    token = "synthetic-local-integration-token"
    headers = {"Authorization": "Bearer " + token}
    with TestClient(create_app(store, token)) as client:
        response = client.get("/api/v1/rubrics/" + rubric["version"], headers=headers)
        assert response.status_code == 200
        assert all(m.get("skill") for m in response.json()["metrics"])
        seeded = client.post("/api/v1/rounds/demo", headers=headers).json()
        queued = client.post(
            "/api/v1/evaluation-runs",
            headers={**headers, "Idempotency-Key": "installed-packages"},
            json={"round_id": seeded["round_id"], "rubric_version": rubric["version"]},
        )
        assert queued.status_code == 202
