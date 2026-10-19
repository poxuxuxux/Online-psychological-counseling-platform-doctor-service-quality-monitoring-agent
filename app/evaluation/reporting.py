# 环节：评价结果后处理层；用途：负责证据校验、评分、风险、报告或统计分析。
from app.domain.models import now
from app.infrastructure.telemetry import usage_summary
from app.team.state import active_findings


def summarize(state):
    profile = state["quality_profile"]
    findings = active_findings(state["team"])
    accepted = [f for mid, f in findings.items() if state["checks"].get(mid, {}).get("accepted")]
    total = profile["overall_score"]
    lines = [
        (
            f"本次为{ {'INITIAL': '初诊', 'FOLLOW_UP': '复诊', 'UNKNOWN': '初复诊未确定'}[state['context']['session_type']] }，"
            f"已完成 {len(findings)}/{len(state['skills']['metrics'])} 项评价记录，"
            f"其中 {len(accepted)} 项通过证据与规则校验。"
        )
    ]
    lines.append(
        f"医生服务质量综合评分为 {total:.2f}/5。"
        if total is not None
        else "当前覆盖度或校验条件不足，未生成综合分数。"
    )
    low = [f for f in accepted if f["score"] is not None and f["score"] < 3]
    if low:
        lines.append(
            "优先改进："
            + "；".join(
                state["skills"]["metrics"][f["metric_id"]]["name"] + "：" + f["reason"]
                for f in low[:3]
            )
            + "。"
        )
    if state["risk"]["requires_manual_review"]:
        lines.append("服务风险或证据缺口需人工复核。")
    return "".join(lines)


def longitudinal(state):
    current = state["quality_profile"]["overall_score"]
    history = state["context"].get("history", [])
    records = []
    for entry in reversed(history):
        r = entry.get("report")
        records.append(
            {
                "session_id": entry["session"]["session_id"],
                "session_time": entry["session"]["session_time"],
                "evaluation_id": r.get("evaluation_id") if r else None,
                "overall_score": r.get("quality_profile", {}).get("overall_score") if r else None,
                "rubric_version": r.get("rubric_version") if r else None,
                "risk": r.get("risk", {}).get("level") if r else None,
                "summary": r.get("summary") if r else None,
            }
        )
    previous = records[-1] if records else None
    comparable = bool(
        previous
        and previous["rubric_version"] == state["skills"]["version"]
        and previous["overall_score"] is not None
        and current is not None
    )
    return {
        "historical_sessions": records,
        "history_limit": state["context"]["history_limit"],
        "comparable": comparable,
        "previous_evaluation_id": previous["evaluation_id"] if previous else None,
        "score_delta": round(current - previous["overall_score"], 3) if comparable else None,
        "trend": "improved"
        if comparable and current > previous["overall_score"]
        else "declined"
        if comparable and current < previous["overall_score"]
        else "stable"
        if comparable
        else "not_comparable",
        "unresolved_service_issues": state["context"].get("follow_up_focus", []),
    }


def build_report(state):
    team, checks, metrics = state["team"], state["checks"], state["skills"]["metrics"]
    agent_results, verifications = [], []
    reasons = list(state["completion"]["issues"])
    for agent, task in team["tasks"].items():
        if task["kind"] != "evaluator":
            continue
        output = []
        for mid, f in task["findings"].items():
            check = checks.get(mid, {})
            evidence = [
                {
                    "message_ids": [team["evidence"][eid]["message_id"]],
                    "quote": team["evidence"][eid]["original_text"],
                    "explanation": f["reason"],
                }
                for eid in f["evidence_ids"]
            ]
            output.append(
                {
                    "finding_id": f["finding_id"],
                    "metric_id": mid,
                    "metric_version": f["metric_version"],
                    "attempt": min(f["revision_count"], 1),
                    "revision_count": f["revision_count"],
                    "supersedes_finding_id": f["supersedes_finding_id"],
                    "applicability": {
                        "EVALUATED": "applicable",
                        "NOT_APPLICABLE": "not_applicable",
                        "NOT_EVALUABLE": "insufficient_context",
                    }[f["status"]],
                    "score": f["score"] if check.get("accepted") else None,
                    "proposed_score": f["score"],
                    "rationale": f["reason"],
                    "evidence": evidence,
                    "limitations": check.get("issues", []),
                    "status": f["status"],
                }
            )
            claims = [
                {
                    "claim_id": f["finding_id"] + f":{i}",
                    "finding_id": f["finding_id"],
                    "claim_type": "absence" if c["polarity"] == "absent" else "observed_behavior",
                    "statement": c["statement"],
                    "subject_role": c["subject"],
                    "behavior": c["behavior"],
                    "negated": c["polarity"] == "absent",
                }
                for i, c in enumerate(f["claims"])
            ]
            verifications.append(
                {
                    "finding_id": f["finding_id"],
                    "reference_status": check.get("reference_status", "uncertain"),
                    "support_status": check.get("support_status", "uncertain"),
                    "applicability_status": check.get("applicability_status", "uncertain"),
                    "rubric_status": check.get("rubric_status", "uncertain"),
                    "claims": claims,
                    "claim_results": [
                        {
                            "claim_id": f["finding_id"] + f":{c['claim_index']}",
                            "status": c["status"],
                            "rationale": c["rationale"],
                            "supporting_evidence": evidence,
                        }
                        for c in check.get("claim_results", [])
                    ],
                    "issues": check.get("issues", []),
                    "notes": check.get("notes", []),
                    "verifier_version": "team-validator-v1",
                    "reference_conflict": "unresolved_conflict" in check.get("issues", []),
                }
            )
            if not check.get("accepted"):
                reasons.append(mid + ": " + ",".join(check.get("issues") or ["not_validated"]))
        agent_results.append(
            {
                "agent_id": agent,
                "status": "completed"
                if task["status"] == "COMPLETED"
                else "partial"
                if output
                else "failed",
                "findings": output,
                "error": task["error"],
            }
        )
    reasons.extend(state["risk"]["reasons"] if state["risk"]["requires_manual_review"] else [])
    issues = [
        mid + ":" + issue for mid, m in metrics.items() for issue in m["configuration_issues"]
    ]
    status = "completed" if state["completion"]["complete"] and not reasons else "partial"
    if len(state["completion"]["missing_metrics"]) == len(metrics):
        status = "failed"
    conflicts = list(team["conflicts"].values())
    return {
        "evaluation_id": state["run_id"],
        "session_id": state["session"]["session_id"],
        "created_at": now(),
        "status": status,
        "schema_version": "2.0",
        "session_type": state["context"]["session_type"],
        "rubric_version": state["skills"]["version"],
        "agent_results": agent_results,
        "verification_results": verifications,
        "quality_profile": state["quality_profile"],
        "risk": state["risk"],
        "summary": state["summary"],
        "summary_status": "completed",
        "summary_method": "grounded_template",
        "longitudinal": state["longitudinal"],
        "limitations": issues,
        "review_required": bool(reasons),
        "review_reasons": list(dict.fromkeys(reasons)),
        "arbitration_status": "unresolved"
        if any(c["status"] != "RESOLVED" for c in conflicts)
        else "resolved"
        if conflicts
        else "not_needed",
        "arbitration_decisions": [
            {
                "conflict_id": c["conflict_id"],
                "metric_ids": c["metric_ids"],
                "status": c["status"].lower(),
                "rationale": c["description"],
                "requires_manual_review": c["status"] != "RESOLVED",
            }
            for c in conflicts
        ],
        "team": {
            "task_count": len(team["tasks"]),
            "message_count": len(team["messages"]),
            "reviewer_count": team["reviews_created"],
            "model_call_count": team["model_calls"],
            "usage": usage_summary(state.get("model_usage", [])),
            "stop_reason": team["stop_reason"],
            "audit_url": f"/api/v1/runs/{state['run_id']}/audit",
        },
        "pipeline_stages": state["completed_stages"],
    }
