import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.agents.structured import StructuredEvaluation
from app.api.local_backend import create_app
from app.api.v1.evaluations import build_demo_session
from app.application.communication import RunCommunicationPool
from app.application.local_worker import run_one
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import snapshot
from tests.test_bounded_review import ReviewProvider
from tests.test_local_backend import HEADERS, TOKEN, FakeProvider


class ManagementSummaryProvider(FakeProvider):
    def __init__(self, manager_mode="valid", summary_mode="valid"):
        super().__init__()
        self.manager_mode = manager_mode
        self.summary_mode = summary_mode
        self.evaluation_contexts = []
        self.summary_input = None

    async def complete(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        output = json.loads(await super().complete(system_prompt, user_prompt))
        if payload.get("task_type") == "management":
            if self.manager_mode == "missing_metric":
                output["tasks"].pop()
            elif self.manager_mode == "wrong_owner":
                output["tasks"][0]["agent_id"] = "empathy_relationship"
            elif self.manager_mode == "invented_message":
                output["events"][0]["message_ids"] = ["foreign-message"]
            elif self.manager_mode == "duplicate_event":
                output["events"].append(output["events"][0])
            elif self.manager_mode == "history":
                output["needs_history"] = True
        elif payload.get("task_type") == "result_summary":
            self.summary_input = payload
            if self.summary_mode == "invented_reference":
                output["observations"][0]["finding_ids"] = ["foreign-finding"]
            elif self.summary_mode == "extra_score":
                output["overall_score"] = 5
            elif self.summary_mode == "score_in_text":
                output["observations"][0]["text"] = "医生获得5分。"
        elif "metrics" in payload:
            self.evaluation_contexts.append(payload["management_context"])
        return json.dumps(output)


@pytest.fixture
def store(tmp_path):
    store = LocalJobStore(tmp_path / "communication.sqlite3")
    session = build_demo_session()
    store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
    return store


async def test_management_context_is_read_from_pool_and_summary_uses_adopted_findings(store):
    provider = ManagementSummaryProvider()
    run_id = store.enqueue(build_demo_session().session_id, "one", snapshot())
    await run_one(store, StructuredEvaluation(provider))
    job = store.job(run_id)
    report = job["report"]
    assert report["management"]["status"] == "completed"
    assert report["summary_status"] == "completed"
    assert len(provider.evaluation_contexts) == 3
    assert all(c["events"][0]["event_id"] == "event-1" for c in provider.evaluation_contexts)
    assert "session" not in provider.summary_input
    assert {f["finding_id"] for f in provider.summary_input["verified_findings"]} == set(
        report["adopted_findings"].values()
    )
    records = LocalJobStore(store.path).pool_records(run_id)
    assert len(records) == report["communication_record_count"]
    assert {"context", "task", "task_status", "finding", "verification", "adoption", "summary"} <= {
        r["kind"] for r in records
    }
    assert all(r["run_id"] == run_id for r in records)
    assert {c["task_record_id"] for c in provider.evaluation_contexts} <= {
        r["record_id"] for r in records if r["kind"] == "task"
    }
    assert report["overall_score"] is None


@pytest.mark.parametrize(
    "mode", ["missing_metric", "wrong_owner", "invented_message", "duplicate_event"]
)
async def test_invalid_manager_plan_falls_back_without_changing_18_tasks(mode):
    provider = ManagementSummaryProvider(manager_mode=mode)
    report = await StructuredEvaluation(provider).run(build_demo_session(), lambda *_: None)
    assert report["management"]["status"] == "fallback"
    assert sum(len(a["findings"]) for a in report["agent_results"]) == 18
    assert all(c["events"] == [] for c in provider.evaluation_contexts)
    assert "management_fallback" in report["limitations"]


@pytest.mark.parametrize("mode", ["invented_reference", "extra_score", "score_in_text"])
async def test_summary_cannot_add_scores_or_unverified_references(mode):
    provider = ManagementSummaryProvider(summary_mode=mode)
    report = await StructuredEvaluation(provider).run(build_demo_session(), lambda *_: None)
    assert report["summary_status"] == "failed"
    assert report["result_summary"] is None
    assert report["overall_score"] is None
    assert sum(len(a["findings"]) for a in report["agent_results"]) == 18


async def test_history_request_does_not_claim_history_was_retrieved():
    report = await StructuredEvaluation(ManagementSummaryProvider(manager_mode="history")).run(
        build_demo_session(), lambda *_: None
    )
    assert "history_requested_but_unavailable" in report["limitations"]


def test_pool_is_isolated_copied_and_append_only(store):
    first = store.enqueue(build_demo_session().session_id, "one", snapshot())
    second = store.enqueue(build_demo_session().session_id, "two", snapshot())
    a, b = RunCommunicationPool(first, store), RunCommunicationPool(second, store)
    record = a.append("context", "manager", {"value": "original"})
    a.read()[0]["payload"]["value"] = "mutated"
    assert a.read()[0]["payload"]["value"] == "original"
    assert b.read() == []
    with pytest.raises(KeyError):
        b.get(record["record_id"])
    with pytest.raises(KeyError):
        b.append("task", "application", {}, correlation_id=record["record_id"])
    with pytest.raises(sqlite3.IntegrityError):
        store.append_pool_record(record)
    with pytest.raises(sqlite3.IntegrityError), store.connect() as db:
        db.execute(
            "UPDATE communication_records SET record_json=? WHERE record_id=?",
            ("{}", record["record_id"]),
        )
    with pytest.raises(sqlite3.IntegrityError), store.connect() as db:
        db.execute("DELETE FROM communication_records WHERE record_id=?", (record["record_id"],))


def test_pool_endpoint_auth_scope_and_cursor(store):
    first = store.enqueue(build_demo_session().session_id, "one", snapshot())
    second = store.enqueue(build_demo_session().session_id, "two", snapshot())
    a, b = RunCommunicationPool(first, store), RunCommunicationPool(second, store)
    a.append("context", "manager", {"label": "first"})
    b.append("context", "manager", {"label": "second"})
    a.append("adoption", "application", {})
    with TestClient(create_app(store, TOKEN)) as client:
        path = f"/api/v1/evaluation-runs/{first}/communication"
        assert client.get(path).status_code == 401
        page = client.get(path + "?limit=1", headers=HEADERS).json()
        next_page = client.get(
            path + f"?after_sequence={page['next_sequence']}", headers=HEADERS
        ).json()
        assert len(page["records"]) == len(next_page["records"]) == 1
        assert page["records"][0]["run_id"] == next_page["records"][0]["run_id"] == first
        assert "second" not in json.dumps([page, next_page])


async def test_pool_persists_revision_and_summary_excludes_unresolved_findings(store):
    run_id = store.enqueue(build_demo_session().session_id, "review", snapshot())
    await run_one(store, StructuredEvaluation(ReviewProvider(still_disputed=True)))
    report = store.job(run_id)["report"]
    records = store.pool_records(run_id)
    assert {"conflict", "arbitration", "revision"} <= {r["kind"] for r in records}
    rejected = {f["finding_id"] for f in report["finding_history"] if f["metric_id"] == "D4.1"}
    summary_task = next(
        r for r in records if r["kind"] == "task" and r["payload"].get("agent_id") == "summary"
    )
    assert not rejected.intersection(summary_task["payload"]["finding_ids"])
    revision = next(r for r in records if r["kind"] == "revision")
    assert revision["supersedes_record_id"] in {
        r["record_id"] for r in records if r["kind"] == "finding"
    }


async def test_no_verified_findings_skips_summary():
    report = await StructuredEvaluation(FakeProvider("invalid_json")).run(
        build_demo_session(), lambda *_: None
    )
    assert report["summary_status"] == "skipped"
    assert report["status"] == "failed"
