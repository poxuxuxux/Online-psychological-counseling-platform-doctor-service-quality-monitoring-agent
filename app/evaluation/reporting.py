# 环节：评价结果后处理层；用途：生成服务总结、纵向分析和评价报告。
from app.domain.models import now
from app.evaluation.scoring import score_eligible
from app.infrastructure.telemetry import usage_summary
from app.team.state import active_findings


def summarize(state):
    profile = state["quality_profile"]
    findings = active_findings(state["team"])
    accepted = [f for mid, f in findings.items() if score_eligible(state, mid, f)]
    total = profile["overall_score"]
    lines = [
        (
            f"本次为{ {'INITIAL': '初诊', 'FOLLOW_UP': '复诊', 'UNKNOWN': '初复诊未确定'}[state['context']['session_type']] }，"
            f"已完成 {len(findings)}/{len(state['skills']['metrics'])} 项评价记录，"
            f"其中 {len(accepted)} 项由 Agent 提交并符合计分输入约束。"
        )
    ]
    lines.append(
        f"医生服务质量综合评分为 {total:.2f}/5。"
        if total is not None
        else "当前指标覆盖度或团队完成度不足，未生成综合分数。"
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
        lines.append("服务风险或评价缺口需人工复核。")
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
    team, metrics = state["team"], state["skills"]["metrics"]
    agent_results = []
    reasons = list(state["completion"]["issues"])
    for agent, task in team["tasks"].items():
        if task["kind"] != "evaluator":
            continue
        output = []
        for mid, f in task["findings"].items():
            accepted = score_eligible(state, mid, f)
            evidence = [
                {
                    "message_ids": [team["evidence"][eid]["message_id"]],
                    "quote": team["evidence"][eid]["original_text"],
                    "explanation": f["reason"],
                }
                for eid in f["evidence_ids"]
                if eid in team["evidence"]
            ]
            output.append(
                {
                    "finding_id": f["finding_id"],
                    "metric_id": mid,
                    "metric_version": f["metric_version"],
                    "attempt": min(f["revision_count"], 1),
                    "revision_count": f["revision_count"],
                    "supersedes_finding_id": f["supersedes_finding_id"],
                    "applicability": (
                        "applicable" if f["status"] == "NOT_EVALUABLE"
                        and ({"rubric_unpublished", "professional_protocol_pending", "timing_policy_pending"}
                             & set(f["review_rule_ids"]))
                        else {
                            "EVALUATED": "applicable",
                            "NOT_APPLICABLE": "not_applicable",
                            "NOT_EVALUABLE": "insufficient_context",
                        }[f["status"]]
                    ),
                    "score": f["score"] if accepted else None,
                    "proposed_score": f["score"],
                    "rationale": f["reason"],
                    "evidence": evidence,
                    "limitations": f["review_rule_ids"],
                    "status": f["status"],
                }
            )
            if f["status"] == "NOT_EVALUABLE":
                reasons.append(mid + ": " + (
                    "timing_policy_pending" if "timing_policy_pending" in f["review_rule_ids"]
                    else "not_evaluable"
                ))
            elif f["status"] == "EVALUATED" and not accepted:
                reasons.append(mid + ": scoring_input_or_conflict")
            elif f["status"] == "NOT_APPLICABLE" and f["review_rule_ids"]:
                reasons.append(mid + ": " + ",".join(f["review_rule_ids"]))
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
    for conflict in team["conflicts"].values():
        if conflict["status"] != "RESOLVED":
            reasons.append("unresolved_conflict:" + conflict["conflict_id"])
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
        "schema_version": "2.1",
        "verification_mode": "none",
        "session_type": state["context"]["session_type"],
        "rubric_version": state["skills"]["version"],
        "agent_results": agent_results,
        "verification_results": [],
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
