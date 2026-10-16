import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents.structured import StructuredEvaluation
from app.api.local_backend import create_app
from app.api.v1.evaluations import build_demo_session
from app.application.communication import RunCommunicationPool
from app.application.hooks.business import DisagreementDetectorHook, RiskMonitorHook
from app.application.local_worker import run_one
from app.domain.models import Finding, Message
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import snapshot
from app.tools.business import RunTools
from tests.test_local_backend import HEADERS, TOKEN, FakeProvider


class SpyHistory:
    def __init__(self, sessions):
        self.sessions = sessions
        self.calls = []

    def for_patient(self, patient):
        self.calls.append(patient)
        return self.sessions


def toolset(session=None, repository=None, authorized=False):
    session = session or build_demo_session()
    return RunTools(session, RunCommunicationPool("test-run"), repository, authorized)


async def test_time_uses_order_start_excludes_notifications_and_counts_voice():
    session = build_demo_session()
    start = session.service_context.consultation_started_at
    session.messages.insert(
        1,
        Message(
            message_id="notification",
            role="doctor",
            message_kind="system_notification",
            content="已接诊",
            sequence=1,
            timestamp=start + timedelta(seconds=30),
        ),
    )
    session.messages.insert(
        2,
        Message(
            message_id="voice",
            role="doctor",
            modality="audio",
            content="",
            sequence=2,
            timestamp=start + timedelta(seconds=60),
        ),
    )
    tools = toolset(session)
    result = await tools.call("process_response", "time_calculator", {"metric_id": "D2.1"})
    assert result["status"] == "completed"
    assert result["data"]["duration_seconds"] == 60
    assert result["data"]["end"]["message_id"] == "voice"
    assert result["data"]["basis"] == "order_timestamp"


async def test_time_missing_order_proxy_and_withdrawal_are_explicit():
    session = build_demo_session()
    session.service_context = None
    result = await toolset(session).call(
        "process_response", "time_calculator", {"metric_id": "D2.1"}
    )
    assert result["data"]["duration_seconds"] is None
    assert "missing_order_start" in result["issues"]
    session = build_demo_session()
    session.service_context.start_basis = "purchase_notification_proxy"
    session.service_context.state = "withdrawn"
    result = await toolset(session).call(
        "process_response", "time_calculator", {"metric_id": "D2.1"}
    )
    assert result["status"] == "partial"
    assert result["data"]["duration_seconds"] == 120
    assert result["data"]["quality"] == "proxy"
    assert "withdrawn_order" in result["issues"]


async def test_interaction_starts_at_first_question_and_rejects_wrong_pairs():
    session = build_demo_session()
    extra = session.messages[0].model_copy(
        update={
            "message_id": "supplement",
            "timestamp": session.messages[0].timestamp + timedelta(seconds=30),
        }
    )
    session.messages.append(extra)
    tools = toolset(session)
    result = await tools.call(
        "process_response",
        "time_calculator",
        {
            "metric_id": "D2.2",
            "question_message_ids": ["demo-m01", "supplement"],
            "reply_message_id": "demo-m02",
        },
    )
    assert result["data"]["duration_seconds"] == 120
    wrong = await tools.call(
        "process_response",
        "time_calculator",
        {"metric_id": "D2.2", "question_message_ids": ["demo-m03"], "reply_message_id": "demo-m02"},
    )
    assert wrong["data"]["duration_seconds"] is None
    assert wrong["issues"] == ["reply_before_question"]


async def test_tool_permissions_and_timestamp_injection_are_rejected():
    tools = toolset()
    denied = await tools.call("summary", "time_calculator", {"metric_id": "D2.1"})
    assert denied["status"] == "denied"
    injected = await tools.call(
        "process_response", "time_calculator", {"metric_id": "D2.1", "start_time": "fake"}
    )
    assert injected["status"] == "failed"
    assert len(tools.pool.read("tool_call")) == len(tools.pool.read("tool_result")) == 2


async def test_evidence_binding_returns_source_time_and_exact_offsets():
    session = build_demo_session()
    quote = "通常几点入睡"
    result = await toolset(session).call(
        "professional_service",
        "evidence_locator",
        {"items": [{"message_id": "demo-m02", "quote": quote}]},
    )
    binding = result["data"]["bindings"][0]
    assert binding["role"] == "doctor"
    assert binding["timestamp"] == session.messages[1].timestamp.isoformat()
    assert binding["span"]["start"] == session.messages[1].content.index(quote)
    assert binding["quote"] == quote
    assert binding["source_snapshot_id"].startswith("snapshot-")


async def test_locator_rejects_fabricated_and_ambiguous_quotes_but_keeps_missing_time():
    session = build_demo_session()
    session.messages[1].content = "你好。你好。"
    session.messages[1].timestamp = None
    tools = toolset(session)
    result = await tools.call(
        "empathy_relationship",
        "evidence_locator",
        {"items": [{"message_id": "demo-m02", "quote": "你好"}]},
    )
    assert result["data"]["item_issues"][0]["code"] == "ambiguous_quote"
    located = await tools.call(
        "empathy_relationship",
        "evidence_locator",
        {"items": [{"message_id": "demo-m02", "quote": "你好", "start_offset": 3}]},
    )
    assert located["data"]["bindings"][0]["timestamp"] is None
    assert located["status"] == "partial"
    bad = await tools.call(
        "empathy_relationship",
        "evidence_locator",
        {"items": [{"message_id": "foreign-history", "quote": "你好"}]},
    )
    assert not bad["data"]["bindings"]
    empty = await tools.call("empathy_relationship", "evidence_locator", {"items": []})
    assert empty["status"] == "failed"


@pytest.mark.parametrize(
    "visit,patient,authorized,expected",
    [
        ("initial", "patient", True, "skipped"),
        ("unknown", "patient", True, "skipped"),
        ("follow_up", None, True, "skipped"),
        ("follow_up", "patient", False, "denied"),
    ],
)
async def test_history_gates_before_repository_access(visit, patient, authorized, expected):
    session = build_demo_session()
    session.consultation_round = visit
    session.anonymized_patient_ref = patient
    repository = SpyHistory([])
    result = await toolset(session, repository, authorized).call(
        "manager", "history_retrieval", {"query": "睡眠"}
    )
    assert result["status"] == expected
    assert repository.calls == []


async def test_follow_up_history_is_dated_scoped_and_has_no_old_scores():
    current = build_demo_session()
    current.consultation_round = "follow_up"
    old = current.model_copy(deep=True)
    old.session_id = "old"
    old.messages[1].timestamp -= timedelta(days=2)
    old.messages = [old.messages[1]]
    wrong = old.model_copy(deep=True)
    wrong.session_id = "another-patient"
    wrong.anonymized_patient_ref = "someone-else"
    future = old.model_copy(deep=True)
    future.session_id = "future"
    future.messages[0].timestamp += timedelta(days=3)
    repository = SpyHistory([current, old, wrong, future])
    result = await toolset(current, repository, True).call(
        "manager", "history_retrieval", {"query": "入睡", "top_k": 3}
    )
    assert repository.calls == [current.anonymized_patient_ref]
    assert len(result["data"]["fragments"]) == 1
    fragment = result["data"]["fragments"][0]
    assert fragment["round_id"] == "old"
    assert fragment["consultation_date"] == old.messages[0].timestamp.date().isoformat()
    assert fragment["source_ref"] and fragment["usage"] == "background_only"
    assert "score" not in json.dumps(result)


class HookProvider(FakeProvider):
    def __init__(self, conflict=False, persistent=False, fail_conflict=False):
        super().__init__()
        self.conflict = conflict
        self.persistent = persistent
        self.fail_conflict = fail_conflict
        self.detect_calls = 0
        self.history_inputs = []
        self.risk_inputs = []

    async def complete(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        task = payload.get("task_type")
        if task == "risk_scan":
            signals = []
            for message in payload["patient_messages"]:
                if "伤害自己" in message["content"]:
                    signals.append(
                        {
                            "message_id": message["message_id"],
                            "quote": message["content"],
                            "referent": "self",
                            "assertion": "negated" if "没有" in message["content"] else "affirmed",
                            "time_scope": "current",
                        }
                    )
            return json.dumps({"signals": signals, "uncertain_message_ids": []})
        if task == "disagreement_detection":
            self.detect_calls += 1
            if self.fail_conflict:
                return '{"winner":"invented"}'
            by_metric = {f["metric_id"]: f for f in payload["verified_findings"]}
            targets = [by_metric.get(mid) for mid in ("D1.1", "D3.4")]
            if (
                self.conflict
                and all(targets)
                and (self.persistent or all(f["attempt"] == 0 for f in targets))
            ):
                return json.dumps(
                    {
                        "conflicts": [
                            {
                                "finding_ids": [f["finding_id"] for f in targets],
                                "explanation": "同一诉求的回应主张互相排斥",
                                "evidence_message_ids": targets[0]["evidence"][0]["message_ids"],
                            }
                        ],
                        "uncertain_pairs": [],
                    }
                )
            return json.dumps({"conflicts": [], "uncertain_pairs": []})
        if "conflicts" in payload:
            return json.dumps(
                {
                    "recommendations": [
                        {
                            "metric_id": c["metric_id"],
                            "action": "re_evaluate",
                            "rationale": "复核当前事件",
                        }
                        for c in payload["conflicts"]
                    ]
                }
            )
        if task == "management":
            self.history_inputs.append(payload["historical_background"])
            self.risk_inputs.append(payload["risk_context"])
        output = json.loads(await super().complete(system_prompt, user_prompt))
        if "metrics" in payload and self.conflict:
            for finding in output["findings"]:
                if finding["metric_id"] == "D1.1":
                    finding["rationale"] = "已经回应患者核心诉求"
                if finding["metric_id"] == "D3.4":
                    finding["rationale"] = (
                        "已经回应患者核心诉求"
                        if payload.get("revision_requests")
                        else "没有回应患者核心诉求"
                    )
        return json.dumps(output)


async def test_risk_hook_records_only_current_affirmed_patient_quotes():
    session = build_demo_session()
    session.messages[0].content = "我现在想伤害自己。"
    session.messages[2].content = "我没有伤害自己的想法。"
    session.messages[1].content = "你是否想伤害自己？"
    tools = toolset(session)
    result = await RiskMonitorHook(HookProvider()).run(session, tools, tools.pool)
    assert result["scan_outcome"] == "detected"
    assert len(result["signals"]) == 1
    assert result["signals"][0]["context_message_ids"] == ["demo-m01"]
    assert result["signals"][0]["target_metric_ids"] == ["D6.1", "D6.2"]
    assert tools.pool.read("evidence_binding")[0]["payload"]["quote"] == session.messages[0].content


async def bound_findings(tools):
    quote = tools.session.messages[1].content
    located = await tools.call(
        "professional_service",
        "evidence_locator",
        {"items": [{"message_id": tools.session.messages[1].message_id, "quote": quote}]},
    )
    findings = [
        Finding(
            metric_id=mid,
            metric_version="unconfigured",
            rationale="test",
            evidence_binding_status="bound",
            evidence_bindings=located["data"]["bindings"],
        )
        for mid in ("D1.1", "D3.4")
    ]
    checks = [
        {"finding_id": f.finding_id, "metric_id": f.metric_id, "status": "supported"}
        for f in findings
    ]
    return findings, checks


async def test_disagreement_uses_only_verified_current_versions_and_deduplicates():
    tools = toolset()
    findings, checks = await bound_findings(tools)
    provider = HookProvider()
    hook = DisagreementDetectorHook(provider, tools.session.session_id, tools.snapshot_id)
    first = await hook.run(findings, checks, snapshot(), tools.pool)
    await hook.run(findings, checks, snapshot(), tools.pool)
    assert provider.detect_calls == 1
    assert first["status"] == "completed" and first["conflicts"] == []
    checks[1]["status"] = "unsupported"
    second = await hook.run(findings, checks, snapshot(), tools.pool)
    assert second["status"] == "skipped"
    assert second["eligible_finding_count"] == 1
    assert provider.detect_calls == 1


async def test_all_five_components_execute_in_follow_up_worker(tmp_path):
    store = LocalJobStore(tmp_path / "integrated.sqlite3")
    with TestClient(create_app(store, TOKEN)) as client:
        seeded = client.post("/api/v1/rounds/demo-follow-up", headers=HEADERS).json()
    session = store.round(seeded["round_id"])["data"]
    session["session_id"] = "risk-follow-up-fixture"
    session["messages"][0]["content"] = "我最近睡眠不好，我现在想伤害自己。"
    store.save_round(session["session_id"], "server_synthetic", session)
    run_id = store.enqueue(session["session_id"], "integrated", snapshot())
    provider = HookProvider(conflict=True)
    await run_one(store, StructuredEvaluation(provider))
    report = store.job(run_id)["report"]
    assert report["risk_scan"]["scan_outcome"] == "detected"
    assert report["historical_background"]["data"]["fragments"]
    assert provider.history_inputs[0]["data"]["fragments"]
    assert provider.risk_inputs[0]["signals"]
    d6 = [t for t in report["management"]["plan"]["tasks"] if t["metric_id"].startswith("D6.")]
    assert len(d6) == 2 and all(t["risk_candidate_ids"] for t in d6)
    assert len(report["management"]["plan"]["tasks"]) == 18
    results = [f for r in report["agent_results"] for f in r["findings"]]
    assert len(results) == 18 and all(f["evidence_binding_status"] == "bound" for f in results)
    assert (
        next(f for f in results if f["metric_id"] == "D2.1")["time_facts"][0]["data"][
            "duration_seconds"
        ]
        == 120
    )
    assert report["disagreement_detection"]["initial"]["conflicts"]
    assert report["disagreement_detection"]["final"]["conflicts"] == []
    assert report["re_evaluation_attempts"] == {"D1.1": 1, "D3.4": 1}
    assert report["unresolved_metrics"] == []
    records = store.pool_records(run_id)
    assert {r["payload"]["tool_name"] for r in records if r["kind"] == "tool_call"} == {
        "time_calculator",
        "history_retrieval",
        "evidence_locator",
    }
    assert {"hook_run", "hook_result", "risk_signal", "conflict_detection", "evidence_binding"} <= {
        r["kind"] for r in records
    }
    stages = [e["stage"] for e in store.job(run_id)["events"]]
    assert (
        stages.index("risk_scanning")
        < stages.index("managing")
        < stages.index("verifying")
        < stages.index("detecting_disagreements")
    )


async def test_unresolved_cross_result_conflict_blocks_summary_claims():
    report = await StructuredEvaluation(HookProvider(conflict=True, persistent=True)).run(
        build_demo_session(), lambda *_: None
    )
    assert report["re_evaluation_attempts"] == {"D1.1": 1, "D3.4": 1}
    assert set(report["unresolved_metrics"]) == {"D1.1", "D3.4"}
    if report["result_summary"]:
        blocked = {
            f["finding_id"]
            for r in report["agent_results"]
            for f in r["findings"]
            if f["metric_id"] in report["unresolved_metrics"]
        }
        assert not blocked.intersection(
            fid for item in report["result_summary"]["observations"] for fid in item["finding_ids"]
        )


async def test_hook_failure_is_not_reported_as_no_conflict():
    report = await StructuredEvaluation(HookProvider(fail_conflict=True)).run(
        build_demo_session(), lambda *_: None
    )
    assert report["disagreement_detection"]["final"]["status"] == "failed"
    assert report["summary_status"] == "skipped"
    assert "disagreement_detection_incomplete" in report["limitations"]
