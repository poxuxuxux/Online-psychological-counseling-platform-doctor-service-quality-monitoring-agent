# 环节：评价结果后处理层；用途：负责证据校验、评分、风险、报告或统计分析。
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def overview(records, catalog, days, source):
    current = datetime.now(ZoneInfo("Asia/Shanghai"))
    end = current.date()
    start = end - timedelta(days=days - 1)
    dated = [
        (r, datetime.fromisoformat(r["created_at"]).astimezone(current.tzinfo).date())
        for r in records
    ]
    dated = [(r, d) for r, d in dated if start <= d <= end]
    same = [(r, d) for r, d in dated if r.get("rubric_version") == catalog.version]
    scored = [
        (r, d)
        for r, d in same
        if r["status"] == "completed"
        and not r["review_required"]
        and r["quality_profile"]["coverage_gate_passed"]
        and r["quality_profile"]["overall_score"] is not None
    ]

    def point(values):
        return {
            "average": round(sum(values) / len(values) * 20, 2) if values else None,
            "sample_count": len(values),
        }

    values = [r["quality_profile"]["overall_score"] for r, _ in scored]
    return {
        "available": True,
        "source": source,
        "days": days,
        "period_start": str(start),
        "period_end": str(end),
        "timezone": "Asia/Shanghai",
        "generated_at": current.isoformat(),
        "rubric_version": catalog.version,
        "score_scale": 100,
        "rules": {"high_quality_min": 85, "risk_below": 60},
        "counts": {
            "evaluated": len(dated),
            "scored": len(scored),
            "high_quality": sum(v * 20 >= 85 for v in values),
            "risk": sum(v * 20 < 60 for v in values),
            "pending": len(same) - len(scored),
            "other_version": len(dated) - len(same),
            "synthetic": sum(r.get("source_id") == "synthetic-demo" for r, _ in dated),
        },
        "average_total": point(values)["average"],
        "dimensions": [
            {
                "dimension_id": dimension,
                "name": dimension,
                **point(
                    [
                        d["score"]
                        for r, _ in scored
                        for d in r["quality_profile"]["dimensions"]
                        if d["dimension_id"] == dimension and d["score"] is not None
                    ]
                ),
            }
            for dimension in catalog.dimensions
        ],
        "trend": [
            {
                "date": str(start + timedelta(days=offset)),
                **point(
                    [
                        r["quality_profile"]["overall_score"]
                        for r, d in scored
                        if d == start + timedelta(days=offset)
                    ]
                ),
            }
            for offset in range(days)
        ],
    }
