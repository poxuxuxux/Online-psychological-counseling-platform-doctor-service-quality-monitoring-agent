import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.agents.structured import StructuredEvaluation
from app.api.local_backend import create_app
from app.api.v1.evaluations import build_demo_session
from app.application.local_worker import run_one
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import CATALOG, VERSION, snapshot

TOKEN = "local-test-token-not-a-real-secret"
HEADERS = {"Authorization": "Bearer " + TOKEN}


class FakeProvider:
    def __init__(self, mode="valid"):
        self.mode = mode
        self.calls = 0

    async def complete(self, system_prompt, user_prompt):
        self.calls += 1
        payload = json.loads(user_prompt)
        if payload.get("task_type") == "risk_scan":
            return json.dumps({"signals": [], "uncertain_message_ids": []})
        if payload.get("task_type") == "response_pairing":
            messages = payload["session"]["messages"]
            patients = [
                m
                for m in messages
                if m["role"] == "patient" and m.get("message_kind", "dialogue") == "dialogue"
            ]
            doctors = [
                m
                for m in messages
                if m["role"] == "doctor" and m.get("message_kind", "dialogue") == "dialogue"
            ]
            return json.dumps(
                {
                    "pairs": [
                        {
                            "question_message_ids": [patients[0]["message_id"]],
                            "reply_message_id": doctors[0]["message_id"] if doctors else None,
                        }
                    ]
                    if patients
                    else []
                }
            )
        if payload.get("task_type") == "disagreement_detection":
            return json.dumps({"conflicts": [], "uncertain_pairs": []})
        if payload.get("task_type") == "management":
            return json.dumps(
                {
                    "context_summary": "合成情境：患者咨询睡眠问题。",
                    "consultation_stage": "information_collection",
                    "needs_history": False,
                    "events": [
                        {
                            "event_id": "event-1",
                            "kind": "patient_concern",
                            "description": "合成诉求",
                            "message_ids": [payload["session"]["messages"][0]["message_id"]],
                            "related_metric_ids": ["D3.1"],
                        }
                    ],
                    "tasks": [
                        {
                            "metric_id": m["metric_id"],
                            "agent_id": m["owner"],
                            "event_ids": ["event-1"],
                        }
                        for m in payload["metric_catalog"]
                    ],
                }
            )
        if payload.get("task_type") == "result_summary":
            return json.dumps(
                {
                    "observations": [
                        {
                            "finding_ids": [payload["verified_findings"][0]["finding_id"]],
                            "text": "医生进行了与本次诉求相关的沟通。",
                        }
                    ],
                    "improvements": [],
                }
            )
        if "metrics" in payload:
            if self.mode == "invalid_json":
                return "PRIVATE MODEL CONTENT"
            message = payload["session"]["messages"][1]
            findings = [
                {
                    "metric_id": m["metric_id"],
                    "score": 5 if self.mode == "scored" else None,
                    "rationale": "合成观察",
                    "evidence": [
                        {
                            "message_ids": [message["message_id"]],
                            "quote": message["content"],
                            "explanation": "直接引用",
                        }
                    ],
                }
                for m in payload["metrics"]
            ]
            if self.mode == "missing_metric":
                findings.pop()
            return json.dumps({"findings": findings})
        assert sorted(m["metric_id"] for m in payload["definitions"]) == sorted(
            f["metric_id"] for f in payload["findings"]
        )
        checks = [
            {"metric_id": f["metric_id"], "status": "supported", "reason": "合成核验"}
            for f in payload["findings"]
        ]
        if self.mode == "missing_check":
            checks.pop()
        return json.dumps({"checks": checks})


@pytest.fixture
def store(tmp_path):
    store = LocalJobStore(tmp_path / "jobs.sqlite3")
    session = build_demo_session()
    store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
    return store


def test_catalog_has_18_unique_metrics_and_fixed_d6_owners():
    assert len({m.metric_id for m in CATALOG}) == 18
    assert Counter(m.owner for m in CATALOG) == {
        "professional_service": 8,
        "process_response": 6,
        "empathy_relationship": 4,
    }
    assert next(m.owner for m in CATALOG if m.metric_id == "D6.1") == "empathy_relationship"
    assert next(m.owner for m in CATALOG if m.metric_id == "D6.2") == "professional_service"


async def test_durable_job_three_agents_verifier_and_no_fake_scores(store):
    run_id = store.enqueue(build_demo_session().session_id, "test", snapshot())
    provider = FakeProvider()
    assert await run_one(store, StructuredEvaluation(provider))
    reopened = LocalJobStore(store.path)
    job = reopened.job(run_id)
    assert job["status"] == "partial"
    assert provider.calls == 9
    findings = [f for a in job["report"]["agent_results"] for f in a["findings"]]
    assert len(findings) == len({f["finding_id"] for f in findings}) == 18
    assert all(f["score"] is None for f in findings)
    assert len(job["report"]["checks"]) == 18
    assert job["report"]["overall_score"] is None
    assert [e["stage"] for e in job["events"]] == [
        "queued",
        "risk_scanning",
        "history_retrieval",
        "managing",
        "evaluating",
        "verifying",
        "detecting_disagreements",
        "summarizing",
        "reporting",
        "partial",
    ]
    assert not await run_one(store, StructuredEvaluation(provider))


@pytest.mark.parametrize("mode", ["scored", "invalid_json", "missing_metric"])
async def test_invalid_agent_outputs_fail_without_leaking_output(store, mode):
    run_id = store.enqueue(build_demo_session().session_id, "test", snapshot())
    await run_one(store, StructuredEvaluation(FakeProvider(mode)))
    job = store.job(run_id)
    assert job["status"] == "failed"
    assert "PRIVATE MODEL CONTENT" not in json.dumps(job)


async def test_incomplete_verifier_results_become_uncertain(store):
    run_id = store.enqueue(build_demo_session().session_id, "test", snapshot())
    await run_one(store, StructuredEvaluation(FakeProvider("missing_check")))
    checks = store.job(run_id)["report"]["checks"]
    assert len(checks) == 18
    assert all(c["status"] == "uncertain" for c in checks)


def test_idempotency_and_single_claim(store):
    rid = build_demo_session().session_id
    run_id = store.enqueue(rid, "key", snapshot())
    assert store.enqueue(rid, "key", snapshot()) == run_id
    with pytest.raises(ValueError, match="idempotency_conflict"):
        store.enqueue("other", "key", snapshot())
    assert store.claim()["id"] == run_id
    assert store.claim() is None
    assert store.recover_interrupted() == 1
    assert store.job(run_id)["status"] == "interrupted"
    assert store.claim() is None  # no automatic replay of paid requests


def test_real_source_cannot_be_enqueued_and_snapshots_cannot_be_overwritten(store):
    store.save_round("raw", "raw_local", {"secret": "private"})
    with pytest.raises(ValueError, match="real_data_evaluation_not_enabled"):
        store.enqueue("raw", "raw-key", snapshot())
    with pytest.raises(ValueError, match="round_snapshot_conflict"):
        store.save_round("raw", "server_synthetic", {})


def test_authenticated_api_enqueue_poll_and_versions(store):
    with TestClient(create_app(store, TOKEN)) as client:
        assert client.get("/api/v1/rounds").status_code == 401
        assert client.get("/api/v1/rounds", headers={"Authorization": "wrong"}).status_code == 401
        assert client.get("/api/v1/rounds", headers=HEADERS).status_code == 200
        seeded = client.post("/api/v1/rounds/demo", headers=HEADERS).json()
        headers = {**HEADERS, "Idempotency-Key": "api-key"}
        response = client.post(
            "/api/v1/evaluation-runs", headers=headers, json={"round_id": seeded["round_id"]}
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        assert (
            client.get(f"/api/v1/evaluation-runs/{run_id}", headers=HEADERS).json()["status"]
            == "queued"
        )
        assert (
            client.get(f"/api/v1/evaluation-runs/{run_id}/report", headers=HEADERS).status_code
            == 409
        )
        assert (
            client.post(
                "/api/v1/evaluation-runs", headers=headers, json={"round_id": seeded["round_id"]}
            ).json()["run_id"]
            == run_id
        )
        assert (
            client.post(
                "/api/v1/evaluation-runs",
                headers=headers,
                json={"round_id": seeded["round_id"], "rubric_version": "wrong"},
            ).status_code
            == 422
        )
        assert (
            len(client.get(f"/api/v1/rubrics/{VERSION}", headers=HEADERS).json()["metrics"]) == 18
        )


def test_local_api_requires_token_before_opening_database(tmp_path):
    with pytest.raises(ValueError, match="LOCAL_API_TOKEN"):
        create_app(token="")
