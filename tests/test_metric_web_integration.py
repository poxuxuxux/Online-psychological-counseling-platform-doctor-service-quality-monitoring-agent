"""The shipped FastAPI app can queue, execute and read a synthetic metric report."""

import asyncio

from fastapi.testclient import TestClient

import app.main as main_module
from app.agents.structured import StructuredEvaluation
from app.application.local_worker import run_one
from app.core.config import Settings
from tests.test_local_backend import FakeProvider


def test_metric_workflow_on_website(monkeypatch, tmp_path):
    access_code = "synthetic-metric-web-test-access-code"
    monkeypatch.setenv("METRIC_RUNS_ACCESS_CODE", access_code)
    monkeypatch.setenv("LOCAL_JOB_DB", str(tmp_path / "metric-jobs.sqlite3"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(main_module, "settings", Settings(database_url=""))

    with TestClient(main_module.app) as client:
        assert client.get("/api/v1/metric-runs/capabilities").json()["enabled"]
        assert client.post("/api/v1/rounds/demo").status_code == 401
        headers = {"X-Metric-Runs-Key": access_code}
        seeded = client.post("/api/v1/rounds/demo", headers=headers)
        assert seeded.status_code == 201
        round_id = seeded.json()["round_id"]
        detail = client.get(f"/api/v1/rounds/{round_id}", headers=headers).json()
        assert detail["data"]["session_id"] == round_id
        created = client.post(
            "/api/v1/evaluation-runs",
            headers={**headers, "Idempotency-Key": "web-test"},
            json={"round_id": round_id},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        assert client.get(f"/api/v1/evaluation-runs/{run_id}/report", headers=headers).status_code == 409
        assert asyncio.run(
            run_one(main_module.app.state.metric_job_store, StructuredEvaluation(FakeProvider()))
        )
        status = client.get(f"/api/v1/evaluation-runs/{run_id}", headers=headers).json()
        assert status["status"] == "partial"
        report = client.get(f"/api/v1/evaluation-runs/{run_id}/report", headers=headers).json()
        assert report["evaluation_id"] == run_id
        assert report["session_id"] == round_id
        assert len(report["rubric"]["metrics"]) == 18
        assert len(report["checks"]) == 18
        assert report["overall_score"] is None
        assert all(
            finding["score"] is None
            for agent in report["agent_results"]
            for finding in agent["findings"]
        )
        assert client.get(f"/api/v1/evaluation-runs/{run_id}/communication", headers=headers).json()[
            "records"
        ]
