# 环节：评价结果后处理层；用途：按医生聚合历史评价并输出版本化监测预警。
"""Doctor-level aggregation over stored reports; alerts are deterministic rules, not model output."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.evaluation.scoring import report_has_score

POLICY_VERSION = "monitoring-v1"
RISK_STREAK_LENGTH = 2
SCORE_DECLINE_STEP = 0.5
DIMENSION_LOW = 3.0
DIMENSION_CRITICAL = 2.5
REVIEW_BACKLOG_LIMIT = 3
RISK_LEVELS = ("high", "medium", "low", "unknown")


def _risk_of(report):
    level = report.get("risk", {}).get("level")
    return level if level in RISK_LEVELS else "unknown"


def _score_of(report):
    return report.get("quality_profile", {}).get("overall_score")


def _scored(report):
    return report_has_score(report)


def _point(values):
    """五分制转百分制；样本数为零时均值为空，不以零分冒充低质量。"""
    return {
        "average": round(sum(values) / len(values) * 20, 2) if values else None,
        "sample_count": len(values),
    }


def _window(records, days, tz):
    end = datetime.now(tz).date()
    start = end - timedelta(days=days - 1)
    kept = []
    for item in records:
        stamp = item["report"].get("created_at")
        if not stamp:
            continue
        try:
            date = datetime.fromisoformat(stamp).astimezone(tz).date()
        except ValueError:
            continue
        if start <= date <= end:
            kept.append({**item, "date": date})
    kept.sort(key=lambda i: (i["date"], i["report"].get("created_at", "")))
    return kept, start, end


def _alert(rule_id, level, message, items):
    sessions = []
    for item in items:
        session_id = item["report"].get("session_id")
        if session_id and session_id not in sessions:
            sessions.append(session_id)
    return {
        "rule_id": rule_id,
        "level": level,
        "message": message,
        "related_sessions": sessions[-3:],
        "last_seen": str(items[-1]["date"]) if items else None,
    }


def monitoring_alerts(comparable, scored, dimensions):
    """规则只引用报告既有事实；阈值集中在此处，随 policy_version 一起版本化。"""
    alerts = []
    if not comparable:
        return alerts
    if _risk_of(comparable[-1]["report"]) == "high":
        alerts.append(
            _alert(
                "latest_high_risk",
                "high",
                "最近一次评价风险等级为高，需优先人工复核。",
                comparable[-1:],
            )
        )
    streak = comparable[-RISK_STREAK_LENGTH:]
    if len(streak) == RISK_STREAK_LENGTH and all(
        _risk_of(i["report"]) in {"medium", "high"} for i in streak
    ):
        alerts.append(
            _alert(
                "consecutive_risk_streak",
                "medium",
                f"最近 {len(streak)} 次评价风险均为中等及以上，建议持续观察。",
                streak,
            )
        )
    flagged = [i for i in comparable if i["report"].get("risk", {}).get("alerts")]
    if flagged:
        alerts.append(
            _alert(
                "serious_service_risk_flag",
                "high",
                "评价期内存在严重服务风险标记；标记单调保留，复核不可取消。",
                flagged,
            )
        )
    if len(scored) >= 2:
        previous = _score_of(scored[-2]["report"])
        current = _score_of(scored[-1]["report"])
        if current - previous <= -SCORE_DECLINE_STEP:
            alerts.append(
                _alert(
                    "score_decline",
                    "medium",
                    f"可信总分连续下滑（{previous:.2f} → {current:.2f}，5 分制），需关注近期服务状态。",
                    scored[-2:],
                )
            )
    weak = [
        d
        for d in dimensions
        if d["average"] is not None
        and d["sample_count"] >= 2
        and d["average"] < DIMENSION_LOW * 20
    ]
    if weak:
        critical = any(d["average"] < DIMENSION_CRITICAL * 20 for d in weak)
        detail = "、".join(f"{d['dimension_id']}（均值 {d['average'] / 20:.1f}/5）" for d in weak)
        alerts.append(
            _alert(
                "persistent_dimension_gap",
                "high" if critical else "medium",
                f"以下维度持续低于 {DIMENSION_LOW}/5：{detail}。",
                scored[-3:],
            )
        )
    backlog = [i for i in comparable if i["report"].get("review_required")]
    if len(backlog) >= REVIEW_BACKLOG_LIMIT:
        alerts.append(
            _alert(
                "review_backlog",
                "medium",
                f"评价期内已有 {len(backlog)} 份报告待人工复核，请关注积压。",
                backlog,
            )
        )
    severity = {"high": 0, "medium": 1}
    return sorted(alerts, key=lambda a: (severity[a["level"]], a["rule_id"]))


def _profile(doctor_id, items, catalog, start, end):
    comparable = [
        i
        for i in items
        if i["report"].get("rubric_version") == catalog.version
        and i["report"].get("status") != "failed"
    ]
    scored = [i for i in comparable if _scored(i["report"])]
    dimensions = [
        {
            "dimension_id": dimension,
            "name": dimension,
            **_point(
                [
                    d["score"]
                    for i in scored
                    for d in i["report"]["quality_profile"]["dimensions"]
                    if d["dimension_id"] == dimension and d["score"] is not None
                ]
            ),
        }
        for dimension in catalog.dimensions
    ]
    trend = [
        {
            "date": str(start + timedelta(days=offset)),
            **_point(
                [
                    _score_of(i["report"])
                    for i in scored
                    if i["date"] == start + timedelta(days=offset)
                ]
            ),
        }
        for offset in range((end - start).days + 1)
    ]
    sessions = [
        {
            "session_id": i["report"].get("session_id"),
            "date": str(i["date"]),
            "overall_score": _score_of(i["report"]),
            "risk_level": _risk_of(i["report"]),
            "review_required": bool(i["report"].get("review_required")),
            "status": i["report"].get("status"),
        }
        for i in reversed(comparable)
    ]
    scores = [_score_of(i["report"]) for i in scored]
    return {
        "doctor_id": doctor_id,
        "counts": {
            "in_window": len(items),
            "comparable": len(comparable),
            "scored": len(scored),
            "pending_review": len(comparable) - len(scored),
            "other_version": len(items) - len(comparable),
        },
        "average_total": _point(scores)["average"],
        "latest_score": _point(scores[-1:])["average"],
        "latest_date": str(scored[-1]["date"]) if scored else None,
        "latest_risk": _risk_of(comparable[-1]["report"]) if comparable else None,
        "dimensions": dimensions,
        "trend": trend,
        "sessions": sessions,
        "alerts": monitoring_alerts(comparable, scored, dimensions),
    }


def doctor_profiles(payload, catalog, days, source):
    tz = ZoneInfo("Asia/Shanghai")
    dated, start, end = _window(payload["records"], days, tz)
    groups = {}
    for item in dated:
        groups.setdefault(item["doctor_id"], []).append(item)
    doctors = []
    for doctor_id, items in groups.items():
        profile = _profile(doctor_id, items, catalog, start, end)
        doctors.append(
            {
                "doctor_id": doctor_id,
                "session_count": profile["counts"]["in_window"],
                "scored_count": profile["counts"]["scored"],
                "average_total": profile["average_total"],
                "latest_score": profile["latest_score"],
                "latest_date": profile["latest_date"],
                "latest_risk": profile["latest_risk"],
                "alerts": [
                    {"rule_id": a["rule_id"], "level": a["level"]} for a in profile["alerts"]
                ],
            }
        )
    doctors.sort(key=lambda d: (d["latest_date"] or "", d["doctor_id"]), reverse=True)
    severity = {"high": 0, "medium": 1}
    doctors.sort(key=lambda d: min((severity[a["level"]] for a in d["alerts"]), default=9))
    return {
        "available": True,
        "source": source,
        "days": days,
        "period_start": str(start),
        "period_end": str(end),
        "timezone": "Asia/Shanghai",
        "generated_at": datetime.now(tz).isoformat(),
        "rubric_version": catalog.version,
        "policy_version": POLICY_VERSION,
        "doctor_count": len(doctors),
        "alert_counts": {
            "high": sum(a["level"] == "high" for d in doctors for a in d["alerts"]),
            "medium": sum(a["level"] == "medium" for d in doctors for a in d["alerts"]),
        },
        "excluded_missing_doctor_id": payload.get("excluded_missing_doctor_id", 0),
        "doctors": doctors,
    }


def doctor_profile(payload, catalog, days, source, doctor_id):
    tz = ZoneInfo("Asia/Shanghai")
    dated, start, end = _window(payload["records"], days, tz)
    items = [i for i in dated if i["doctor_id"] == doctor_id]
    if not items:
        return None
    return {
        "available": True,
        "source": source,
        "days": days,
        "period_start": str(start),
        "period_end": str(end),
        "timezone": "Asia/Shanghai",
        "generated_at": datetime.now(tz).isoformat(),
        "rubric_version": catalog.version,
        "policy_version": POLICY_VERSION,
        **_profile(doctor_id, items, catalog, start, end),
    }
