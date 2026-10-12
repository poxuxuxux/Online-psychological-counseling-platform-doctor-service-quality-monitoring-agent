"""Read-only cohort statistics. This module never generates or revises clinical scores."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from statistics import mean
from typing import Any

from pydantic import ValidationError

from app.domain.models import EvaluationReport

SHANGHAI = timezone(timedelta(hours=8))
DIMENSIONS = (
    ("D1", "服务履行"),
    ("D2", "响应及时性"),
    ("D3", "专业信息与回应"),
    ("D4", "共情与关系"),
    ("D5", "协作与建议"),
    ("D6", "风险回应与转介"),
)
METRIC_COUNTS = {"D1": 2, "D2": 2, "D3": 5, "D4": 3, "D5": 4, "D6": 2}
FORMAL_METRICS = {f"{dim}.{n}" for dim, count in METRIC_COUNTS.items() for n in range(1, count + 1)}


def statistics_period(days: int, now: datetime) -> tuple[datetime, datetime]:
    """Inclusive calendar days in Asia/Shanghai; UTC storage dates remain aware."""
    today = now.astimezone(SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days - 1), today + timedelta(days=1)


def trusted_snapshot(report: EvaluationReport) -> tuple[str, float, dict[str, float]] | None:
    """Require explicit semantic/anchor checks and a consistent published profile.

    Existing keyword demo results cannot pass this gate. A missing score is not zero.
    Superseded originals are retained in storage but never counted twice.
    """
    profile = report.quality_profile
    if (
        report.status != "completed"
        or report.review_required
        or report.arbitration_status not in {"resolved", "not_needed"}
        or profile is None
        or not profile.coverage_gate_passed
        or profile.overall_score is None
    ):
        return None
    rows = [(a, f) for a in report.agent_results for f in a.findings]
    ids = [f.finding_id for _, f in rows]
    if len(set(ids)) != len(ids):
        return None
    superseded = set()
    for agent, finding in rows:
        if finding.supersedes_finding_id:
            prior = [(a, f) for a, f in rows if f.finding_id == finding.supersedes_finding_id]
            if (
                finding.attempt != 1
                or len(prior) != 1
                or prior[0][1].attempt != 0
                or prior[0][0].agent_id != agent.agent_id
                or prior[0][1].metric_id != finding.metric_id
            ):
                return None
            superseded.add(finding.supersedes_finding_id)
    active = [(a, f) for a, f in rows if f.finding_id not in superseded]
    metric_ids = [f.metric_id for _, f in active]
    if (
        not active
        or len(set(metric_ids)) != len(metric_ids)
        or not set(metric_ids) <= FORMAL_METRICS
    ):
        return None
    versions = {f.metric_version for _, f in active}
    if len(versions) != 1 or None in versions or "" in versions:
        return None
    scored = {}
    for agent, finding in active:
        checks = [v for v in report.verification_results if v.finding_id == finding.finding_id]
        if agent.status != "completed" or len(checks) != 1:
            return None
        check = checks[0]
        if check.reference_conflict or check.applicability_status != "matched" or check.issues:
            return None
        if finding.applicability == "not_applicable":
            if finding.score is not None:
                return None
            continue
        claim_ids = [c.claim_id for c in check.claims]
        results = check.claim_results
        if (
            finding.applicability != "applicable"
            or finding.score is None
            or check.reference_status != "valid"
            or check.support_status != "supported"
            or check.rubric_status != "matched"
            or not claim_ids
            or len(set(claim_ids)) != len(claim_ids)
            or any(c.finding_id != finding.finding_id for c in check.claims)
            or len(results) != len(claim_ids)
            or {c.claim_id for c in results} != set(claim_ids)
            or any(c.status != "supported" for c in results)
            or not finding.evidence
            or any(not e.message_ids or not e.quote.strip() for e in finding.evidence)
        ):
            return None
        scored[finding.metric_id] = finding.score
    if not scored:
        return None
    dim_ids = [d.dimension_id for d in profile.dimensions]
    if len(set(dim_ids)) != len(dim_ids) or not set(dim_ids) <= set(METRIC_COUNTS):
        return None
    linked = {}
    dimension_scores = {}
    for dimension in profile.dimensions:
        applicable = [m for m in dimension.metric_scores if m.applicability == "applicable"]
        if applicable and (dimension.score is None or dimension.coverage <= 0):
            return None
        if not applicable and dimension.score is not None:
            return None
        for metric in applicable:
            if (
                metric.dimension_id != dimension.dimension_id
                or not metric.metric_id.startswith(dimension.dimension_id + ".")
                or metric.metric_id in linked
                or metric.score != scored.get(metric.metric_id)
            ):
                return None
            linked[metric.metric_id] = metric.score
        if dimension.score is not None:
            dimension_scores[dimension.dimension_id] = dimension.score * 20
    if set(linked) != set(scored):
        return None
    return next(iter(versions)), profile.overall_score * 20, dimension_scores


def build_overview(
    records: list[dict[str, Any]],
    days: int = 30,
    now: datetime | None = None,
    available: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    start, end = statistics_period(days, now)
    # Select latest run across all history FIRST; then apply the period to its saved date.
    latest = {}
    for row in records:
        key = row["session_id"]
        if key not in latest or (row["created_at"], row["evaluation_id"]) > (
            latest[key]["created_at"],
            latest[key]["evaluation_id"],
        ):
            latest[key] = row
    cohort = sorted(
        (r for r in latest.values() if start <= r["created_at"] < end),
        key=lambda r: (r["created_at"], r["evaluation_id"]),
        reverse=True,
    )
    valid = []
    for row in cohort:
        try:
            report = EvaluationReport.model_validate(row["report_data"])
            if (
                report.session_id != row["session_id"]
                or report.evaluation_id != row["evaluation_id"]
            ):
                continue
            snapshot = trusted_snapshot(report)
        except (ValidationError, TypeError, ValueError):
            continue
        if snapshot:
            valid.append((row, snapshot))
    version = valid[0][1][0] if valid else None
    selected = [(r, s) for r, s in valid if s[0] == version]
    totals = [s[1] for _, s in selected]
    buckets = defaultdict(list)
    dimension_buckets = defaultdict(list)
    for row, snapshot in selected:
        buckets[row["created_at"].astimezone(SHANGHAI).date().isoformat()].append(snapshot[1])
        for dimension, score in snapshot[2].items():
            dimension_buckets[dimension].append(score)
    nullable = lambda number: number if available else None
    return {
        "available": available,
        "source": "postgresql",
        "days": days,
        "period_start": start.date().isoformat(),
        "period_end": (end - timedelta(days=1)).date().isoformat(),
        "timezone": "Asia/Shanghai",
        "generated_at": now.isoformat(),
        "rubric_version": version,
        "score_scale": 100,
        "rules": {"high_quality_min": 85, "risk_below": 60},
        "counts": {
            "evaluated": nullable(len(cohort)),
            "scored": nullable(len(selected)),
            "high_quality": nullable(sum(s >= 85 for s in totals)),
            "risk": nullable(sum(s < 60 for s in totals)),
            "pending": nullable(len(cohort) - len(valid)),
            "other_version": nullable(len(valid) - len(selected)),
            "synthetic": nullable(
                sum(r.get("source_id") in {"synthetic-demo", "offline-preview"} for r in cohort)
            ),
        },
        "average_total": round(mean(totals), 2) if totals else None,
        "dimensions": [
            {
                "dimension_id": dim,
                "name": name,
                "average": round(mean(dimension_buckets[dim]), 2)
                if dimension_buckets[dim]
                else None,
                "sample_count": len(dimension_buckets[dim]),
            }
            for dim, name in DIMENSIONS
        ],
        "trend": [
            {
                "date": (start + timedelta(days=i)).date().isoformat(),
                "average": round(mean(buckets[date]), 2) if buckets[date] else None,
                "sample_count": len(buckets[date]),
            }
            for i in range(days)
            for date in [(start + timedelta(days=i)).date().isoformat()]
        ],
    }
