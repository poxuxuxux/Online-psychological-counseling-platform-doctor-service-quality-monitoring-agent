"""Statistics must preserve trust gates, thresholds, dates and consultation denominators."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.domain.models import EvaluationReport
from app.evaluation.analytics import build_overview, statistics_period, trusted_snapshot
from app.infrastructure.repositories.evaluations import PostgresEvaluationStore
from app.main import app

NOW = datetime(2026, 10, 12, 8, tzinfo=UTC)


def record(session="s1", evaluation="e1", score=4.25, version="formal-v1", at=None):
    evidence = {
        "message_ids": ["m1"],
        "quote": "谢谢你说得这么具体",
        "explanation": "synthetic test",
    }
    finding = {
        "finding_id": "f1",
        "metric_id": "D4.1",
        "metric_version": version,
        "score": score,
        "rationale": "synthetic test",
        "evidence": [evidence],
    }
    check = {
        "finding_id": "f1",
        "reference_status": "valid",
        "support_status": "supported",
        "applicability_status": "matched",
        "rubric_status": "matched",
        "claims": [
            {
                "claim_id": "c1",
                "finding_id": "f1",
                "claim_type": "observed_behavior",
                "statement": "synthetic test",
            }
        ],
        "claim_results": [{"claim_id": "c1", "status": "supported"}],
    }
    report = {
        "session_id": session,
        "evaluation_id": evaluation,
        "status": "completed",
        "arbitration_status": "not_needed",
        "agent_results": [
            {"agent_id": "empathy_relationship", "status": "completed", "findings": [finding]}
        ],
        "verification_results": [check],
        "quality_profile": {
            "overall_score": score,
            "coverage_gate_passed": True,
            "dimensions": [
                {
                    "dimension_id": "D4",
                    "name": "共情与关系",
                    "score": score,
                    "coverage": 1,
                    "metric_scores": [{"dimension_id": "D4", "metric_id": "D4.1", "score": score}],
                }
            ],
        },
    }
    return {
        "session_id": session,
        "evaluation_id": evaluation,
        "report_data": report,
        "created_at": at or NOW,
        "source_id": "synthetic-demo",
    }


def test_exact_user_thresholds_and_conversion():
    result = build_overview(
        [record(str(i), str(i), score=s) for i, s in enumerate([4.25, 4.249, 3, 2.999, 5, 0])],
        now=NOW,
    )
    assert result["counts"] == {
        "evaluated": 6,
        "scored": 6,
        "high_quality": 2,
        "risk": 2,
        "pending": 0,
        "other_version": 0,
        "synthetic": 6,
    }
    assert result["average_total"] == 64.99
    assert result["dimensions"][3]["sample_count"] == 6


def test_repeated_runs_count_once_and_latest_failed_run_does_not_reuse_old_score():
    old = record(evaluation="old", at=NOW - timedelta(hours=1))
    latest = record(evaluation="new")
    latest["report_data"]["status"] = "failed"
    result = build_overview([old, latest], now=NOW)
    assert result["counts"]["evaluated"] == 1
    assert result["counts"]["scored"] == 0
    assert result["counts"]["pending"] == 1
    assert result["average_total"] is None


def test_semantic_and_anchor_checks_are_required_not_merely_quote_location():
    for field, value in [
        ("claims", []),
        ("claim_results", []),
        ("rubric_status", "uncertain"),
        ("applicability_status", "uncertain"),
        ("reference_conflict", True),
        ("issues", ["scope unknown"]),
        ("support_status", "partial"),
    ]:
        row = record()
        row["report_data"]["verification_results"][0][field] = value
        assert build_overview([row], now=NOW)["counts"]["scored"] == 0


def test_missing_profile_unresolved_conflict_or_review_required_excluded():
    for field, value in [
        ("quality_profile", None),
        ("arbitration_status", "unresolved"),
        ("arbitration_status", "not_configured"),
        ("review_required", True),
    ]:
        row = record()
        row["report_data"][field] = value
        assert build_overview([row], now=NOW)["counts"]["scored"] == 0


def test_duplicate_checks_or_claim_results_are_not_accepted():
    row = record()
    checks = row["report_data"]["verification_results"]
    checks.append(deepcopy(checks[0]))
    assert build_overview([row], now=NOW)["counts"]["scored"] == 0
    row = record()
    results = row["report_data"]["verification_results"][0]["claim_results"]
    results.append(deepcopy(results[0]))
    assert build_overview([row], now=NOW)["counts"]["scored"] == 0


def test_explicit_revision_replaces_original_and_profile_must_use_new_score():
    row = record()
    report = row["report_data"]
    findings = report["agent_results"][0]["findings"]
    old = deepcopy(findings[0])
    old.update(finding_id="old", score=1)
    findings.insert(0, old)
    findings[1].update(attempt=1, supersedes_finding_id="old")
    assert build_overview([row], now=NOW)["counts"]["scored"] == 1
    report["quality_profile"]["dimensions"][0]["metric_scores"][0]["score"] = 1
    assert build_overview([row], now=NOW)["counts"]["scored"] == 0


def test_duplicate_metrics_unknown_demo_metrics_and_unlinked_profile_are_rejected():
    row = record()
    findings = row["report_data"]["agent_results"][0]["findings"]
    duplicate = deepcopy(findings[0])
    duplicate["finding_id"] = "f2"
    findings.append(duplicate)
    assert build_overview([row], now=NOW)["counts"]["scored"] == 0
    row = record()
    row["report_data"]["agent_results"][0]["findings"][0]["metric_id"] = "D4"
    assert build_overview([row], now=NOW)["counts"]["scored"] == 0
    row = record()
    row["report_data"]["quality_profile"]["dimensions"][0]["metric_scores"] = []
    assert trusted_snapshot(EvaluationReport.model_validate(row["report_data"])) is None


def test_no_zero_filling_and_natural_day_grouping_in_shanghai():
    row = record(at=datetime(2026, 10, 11, 17, tzinfo=UTC))  # 12th in Shanghai
    result = build_overview([row], days=7, now=NOW)
    assert result["period_start"] == "2026-10-06"
    assert result["trend"][-1] == {"date": "2026-10-12", "average": 85, "sample_count": 1}
    assert result["trend"][0]["average"] is None
    assert result["dimensions"][0]["average"] is None
    assert result["dimensions"][0]["sample_count"] == 0


def test_range_filter_is_after_deduplication_and_version_cohorts_are_not_mixed():
    start, _ = statistics_period(7, NOW)
    old = record(evaluation="old", at=start - timedelta(seconds=1))
    new = record(evaluation="new", at=NOW)
    second = record(session="s2", evaluation="e2", version="v2", at=NOW + timedelta(minutes=1))
    result = build_overview([old, new, second], days=7, now=NOW)
    assert result["counts"]["evaluated"] == 2
    assert result["counts"]["scored"] == 1
    assert result["counts"]["other_version"] == 1
    assert result["rubric_version"] == "v2"


def test_database_unconfigured_is_unknown_and_invalid_stored_report_is_pending():
    result = build_overview([], now=NOW, available=False)
    assert all(c is None for c in result["counts"].values())
    row = record()
    row["report_data"]["quality_profile"]["overall_score"] = 99
    assert build_overview([row], now=NOW)["counts"]["pending"] == 1


def test_api_no_database_and_range_validation():
    with TestClient(app) as client:
        result = client.get("/api/v1/evaluations/overview?days=7")
        assert result.status_code == 200
        assert result.json()["available"] is False
        assert result.json()["counts"]["evaluated"] is None
        assert client.get("/api/v1/evaluations/overview?days=91").status_code == 422


def test_api_database_failure_does_not_expose_credentials(monkeypatch):
    monkeypatch.setattr(PostgresEvaluationStore, "configured", property(lambda _: True))

    async def initialize(_):
        pass

    async def broken(*_):
        raise RuntimeError("postgres://user:SECRET@example.invalid/db")

    monkeypatch.setattr(PostgresEvaluationStore, "initialize", initialize)
    monkeypatch.setattr(PostgresEvaluationStore, "overview_records", broken)
    with TestClient(app) as client:
        result = client.get("/api/v1/evaluations/overview")
        assert result.status_code == 503
        assert "SECRET" not in result.text


async def test_store_parameterized_latest_first_query():
    queries = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, query, parameters):
            queries.append((query, parameters))
            return self

        async def fetchall(self):
            return []

    store = PostgresEvaluationStore("postgresql://test.invalid/db")

    async def connect():
        return Connection()

    store._connect = connect
    start, end = statistics_period(7, NOW)
    assert await store.overview_records(start, end) == []
    query, parameters = queries[0]
    assert "DISTINCT ON (session_id)" in query
    assert query.index("DISTINCT ON") < query.index("WHERE r.created_at")
    assert parameters == (start, end)
