# 环节：评价结果后处理层；用途：汇总 Agent 评分并计算服务质量风险。
from app.team.state import active_findings


def score_eligible(state, mid, finding):
    """Use an assigned Agent's structured result; no independent semantic model pass."""
    if not finding or finding["status"] != "EVALUATED" or finding["score"] is None:
        return False
    spec = state["skills"]["metrics"][mid]
    if (
        spec["status"] != "published"
        or spec["configuration_issues"]
        or finding["score"] not in spec["score_values"]
        or finding["review_rule_ids"]
        or not finding["evidence_ids"]
        or not finding["claims"]
    ):
        return False
    if any(eid not in state["team"]["evidence"] for eid in finding["evidence_ids"]):
        return False
    return not any(
        conflict["status"] != "RESOLVED" and mid in conflict["metric_ids"]
        for conflict in state["team"]["conflicts"].values()
    )


def score(state):
    metrics = state["skills"]["metrics"]
    findings = active_findings(state["team"])
    dimensions, total_weight, weighted, required, accepted = [], 0, 0, 0, 0
    for dimension in state["dimension_ids"]:
        items = []
        for mid, spec in metrics.items():
            if spec["dimension_id"] != dimension:
                continue
            f = findings.get(mid)
            if f and f["status"] == "NOT_APPLICABLE" and not f["review_rule_ids"]:
                continue
            value = f["score"] if score_eligible(state, mid, f) else None
            items.append((value, spec["weight"]))
        count = sum(value is not None for value, _ in items)
        coverage = count / len(items) if items else 1.0
        weight = sum(w for _, w in items)
        subtotal = sum(value * w for value, w in items if value is not None)
        dimensions.append(
            {
                "dimension_id": dimension,
                "name": dimension,
                "score": round(subtotal / weight, 3) if items and coverage == 1 else None,
                "coverage": coverage,
            }
        )
        required += len(items)
        accepted += count
        total_weight += weight
        weighted += subtotal
    coverage = accepted / required if required else 1.0
    complete = state["completion"]["complete"]
    gate = bool(required and coverage == 1 and complete)
    return {
        "dimensions": dimensions,
        "overall_coverage": coverage,
        "overall_score": round(weighted / total_weight, 3) if gate else None,
        "coverage_gate_passed": gate,
        "aggregation": "skill_weighted_mean",
        "scale": [0, 5],
        "evaluated_count": accepted,
        "required_count": required,
    }


def classify_risk(state):
    profile, team = state["quality_profile"], state["team"]
    findings = active_findings(team)
    flags = team["risk_alerts"]
    if flags:
        level, reasons = "high", ["serious_service_risk_requires_human_review"]
    elif any(
        f["risk"] == "service_gap" and score_eligible(state, mid, f)
        for mid, f in findings.items()
    ):
        level, reasons = "medium", ["agent_reported_service_gap"]
    elif profile["overall_score"] is None:
        level, reasons = "unknown", ["insufficient_scored_coverage"]
    elif profile["overall_score"] < 3:
        level, reasons = "high", ["service_quality_score_below_3"]
    elif profile["overall_score"] < 4:
        level, reasons = "medium", ["service_quality_score_below_4"]
    else:
        level, reasons = "low", []
    return {
        "level": level,
        "scope": "doctor_service_quality",
        "policy_version": "service-risk-v1",
        "reasons": reasons,
        "alerts": flags,
        "requires_manual_review": level in {"high", "unknown"},
    }
