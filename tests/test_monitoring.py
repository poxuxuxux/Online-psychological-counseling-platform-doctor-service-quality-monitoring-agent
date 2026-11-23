# 环节：评价结果后处理层；用途：验证医生画像聚合与确定性预警规则。
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.evaluation.monitoring import POLICY_VERSION, doctor_profile, doctor_profiles

CATALOG = SimpleNamespace(version="skills-test", dimensions=["D1", "D2", "D3", "D4", "D5", "D6"])


def stamp(days_ago=0):
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def record(doctor_id, session_id, days_ago, **overrides):
    report = {
        "session_id": session_id,
        "created_at": stamp(days_ago),
        "status": "completed",
        "review_required": False,
        "rubric_version": CATALOG.version,
        "risk": {"level": "low", "alerts": []},
        "quality_profile": {
            "coverage_gate_passed": True,
            "overall_score": 4.0,
            "dimensions": [{"dimension_id": d, "score": 4.0} for d in CATALOG.dimensions],
        },
    }
    report.update(overrides)
    return {"doctor_id": doctor_id, "report": report}


def payload(*records, excluded=0):
    return {"records": list(records), "excluded_missing_doctor_id": excluded}


def profile_with(overall, dimension_score):
    return {
        "coverage_gate_passed": True,
        "overall_score": overall,
        "dimensions": [{"dimension_id": d, "score": dimension_score} for d in CATALOG.dimensions],
    }


def test_doctors_grouped_and_alerted_sorted_first():
    healthy = record("dr-1", "s-good", 1)
    declining = [
        record("dr-2", "s-bad-old", 20, quality_profile=profile_with(2.6, 2.4)),
        record("dr-2", "s-bad", 0, risk={"level": "high", "alerts": []},
               quality_profile=profile_with(2.2, 2.0)),
    ]
    result = doctor_profiles(payload(healthy, *declining, excluded=2), CATALOG, 180, "sqlite")
    assert result["policy_version"] == POLICY_VERSION
    assert result["doctor_count"] == 2
    assert result["excluded_missing_doctor_id"] == 2
    assert [d["doctor_id"] for d in result["doctors"]] == ["dr-2", "dr-1"]
    top = result["doctors"][0]
    assert {a["rule_id"] for a in top["alerts"]} >= {"latest_high_risk", "persistent_dimension_gap"}
    assert result["alert_counts"]["high"] >= 2


def test_score_decline_and_dimension_gap_alerts():
    old = record("dr-9", "s-old", 60, quality_profile=profile_with(4.5, 2.0))
    new = record("dr-9", "s-new", 1, quality_profile=profile_with(3.8, 2.2))
    profile = doctor_profile(payload(old, new), CATALOG, 180, "sqlite", "dr-9")
    rules = {a["rule_id"] for a in profile["alerts"]}
    assert "score_decline" in rules
    assert "persistent_dimension_gap" in rules
    gap = next(a for a in profile["alerts"] if a["rule_id"] == "persistent_dimension_gap")
    assert gap["level"] == "high"
    assert profile["counts"]["scored"] == 2
    assert profile["latest_score"] == 76.0
    assert profile["latest_date"] is not None


def test_pending_and_other_version_reports_do_not_score():
    pending = record(
        "dr-7",
        "s-pending",
        2,
        review_required=True,
        quality_profile=profile_with(None, None),
    )
    pending["report"]["quality_profile"]["coverage_gate_passed"] = False
    scored = record("dr-7", "s-scored", 0)
    other = record("dr-7", "s-old-version", 3, rubric_version="skills-old")
    profile = doctor_profile(payload(pending, scored, other), CATALOG, 180, "sqlite", "dr-7")
    assert profile["counts"]["scored"] == 1
    assert profile["counts"]["pending_review"] == 1
    assert profile["counts"]["other_version"] == 1
    assert profile["trend"][-1]["sample_count"] == 1
    assert any(s["review_required"] for s in profile["sessions"])


def test_review_backlog_alert():
    records = [
        record(
            "dr-5",
            f"s-{i}",
            i,
            review_required=True,
            quality_profile=profile_with(None, None),
        )
        for i in range(3)
    ]
    profile = doctor_profile(payload(*records), CATALOG, 180, "sqlite", "dr-5")
    assert any(a["rule_id"] == "review_backlog" for a in profile["alerts"])


def test_consecutive_risk_streak_alert():
    first = record("dr-3", "s-a", 10, risk={"level": "medium", "alerts": []})
    second = record("dr-3", "s-b", 2, risk={"level": "medium", "alerts": []})
    profile = doctor_profile(payload(first, second), CATALOG, 180, "sqlite", "dr-3")
    assert any(a["rule_id"] == "consecutive_risk_streak" for a in profile["alerts"])


def test_unknown_doctor_returns_none():
    assert (
        doctor_profile(payload(record("dr-1", "s1", 1)), CATALOG, 180, "sqlite", "nobody") is None
    )
