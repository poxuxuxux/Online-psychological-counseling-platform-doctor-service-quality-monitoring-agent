# 环节：评价结果后处理层；用途：汇总 Agent 评分并计算服务质量风险。
from app.team.state import active_findings
from app.team.weights import bounded_weights, normalize_weights

SCORE_POLICY_VERSION = "eligible-metrics-v2"


def report_has_score(report):
    """One policy for current reports; preserve conservative gates for legacy reports."""
    profile = report.get("quality_profile") or {}
    valid = (profile.get("coverage_gate_passed") and profile.get("overall_score") is not None
             and report.get("arbitration_status") != "unresolved"
             and report.get("status") != "failed")
    if profile.get("policy_version") == SCORE_POLICY_VERSION:
        return bool(valid)
    return bool(valid and report.get("status") == "completed" and not report.get("review_required"))


def score_eligible(state, mid, finding):
    """Use an assigned Agent's structured result; no independent semantic model pass."""
    if not finding or finding["status"] != "EVALUATED" or finding["score"] is None:
        return False
    if state["team"].get("protocol") not in {"leader-review-v1", "leader-review-v2"} and any(
        mid in t.get("submission_errors", {}) for t in state["team"]["tasks"].values()
    ):
        return False
    spec = state["skills"]["metrics"][mid]
    if (
        spec["status"] != "published"
        or spec["configuration_issues"]
        or spec.get("scoring_blockers")
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
    is_lead = state["team"].get("protocol") in {"leader-review-v1", "leader-review-v2"}
    if is_lead:
        selected = state.get("team_plan", {}).get("selected_metric_ids", [])
        metrics = {mid: metrics[mid] for mid in selected}
        candidates = {mid: state["team_plan"]["weights"][mid] for mid, spec in metrics.items()
                      if spec["status"] == "published" and not spec.get("scoring_blockers")
                      and not (findings.get(mid, {}).get("status") == "NOT_APPLICABLE"
                               and not findings[mid]["review_rule_ids"])}
        effective = (normalize_weights(candidates) if state["team"].get("protocol") == "leader-review-v2"
                     else bounded_weights(candidates, state["team_plan"].get("weight_deviation", .2)))
    else:
        effective = {mid: spec["weight"] for mid, spec in metrics.items()}
    dimensions, total_weight, weighted, required, accepted, exclusions = [], 0, 0, 0, 0, []
    for dimension in state["dimension_ids"]:
        items = []
        for mid, spec in metrics.items():
            if spec["dimension_id"] != dimension:
                continue
            f = findings.get(mid)
            if f and f["status"] == "NOT_APPLICABLE" and not f["review_rule_ids"]:
                continue
            if spec["status"] != "published" or spec.get("scoring_blockers"):
                # 配置上永远无法数值计分的指标不参与覆盖门控，单独披露而不是拖垮总分。
                exclusions.append(
                    {
                        "metric_id": mid,
                        "reason": (
                            "rubric_not_published"
                            if spec["status"] != "published"
                            else "scoring_blocked_by_configuration"
                        ),
                        "scoring_blockers": sorted(spec.get("scoring_blockers", [])),
                    }
                )
                continue
            value = f["score"] if score_eligible(state, mid, f) else None
            items.append((value, effective[mid]))
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
    complete = state["completion"].get("scoring_complete", state["completion"]["complete"])
    gate = bool(required and coverage == 1 and complete)
    result = {
        "policy_version": SCORE_POLICY_VERSION,
        "dimensions": dimensions,
        "overall_coverage": coverage,
        "overall_score": round(weighted / total_weight, 3) if gate else None,
        "coverage_gate_passed": gate,
        "aggregation": "skill_weighted_mean",
        "scale": [0, 5],
        "evaluated_count": accepted,
        "required_count": required,
        "score_exclusions": exclusions,
    }
    if is_lead:
        import hashlib
        import json
        result.update(weights=effective, selected_metric_ids=list(metrics),
                      assigned_weights=state.get("team_plan", {}).get("weights", {}),
                      weight_policy=state["team_plan"].get("weight_policy", "bounded-equal-simplex-v1"),
                      protocol=state["team"]["protocol"],
                      weight_deviation=state.get("team_plan", {}).get("weight_deviation", .2))
        signature = {key: result[key] for key in ("weights", "selected_metric_ids", "weight_policy", "protocol", "weight_deviation")}
        result["scoring_signature"] = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:20]
    return result


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
