# 环节：评价结果后处理层；用途：生成服务总结、纵向分析和评价报告。
from app.domain.models import now
from app.evaluation.scoring import score_eligible
from app.infrastructure.telemetry import usage_summary
from app.team.state import active_findings


def finding_outcome(state, mid, finding):
    """Do not turn infrastructure failures or review policies into missing evidence."""
    if finding.get("origin") == "runtime_fallback":
        return "execution_failed"
    if finding["status"] == "NOT_APPLICABLE" and not finding["review_rule_ids"]:
        return "not_applicable"
    spec = state["skills"]["metrics"][mid]
    if spec["status"] != "published" or spec.get("scoring_blockers"):
        return "configuration_blocked"
    if any(c["status"] != "RESOLVED" and mid in c["metric_ids"]
           for c in state["team"]["conflicts"].values()):
        return "conflict"
    if score_eligible(state, mid, finding):
        return "scored"
    rules = set(finding["review_rule_ids"])
    if rules & {"source_incomplete", "context_ambiguous", "source_conflict", "time_facts_missing"}:
        return "insufficient_evidence"
    return "manual_review"


def summarize(state):
    profile = state["quality_profile"]
    findings = active_findings(state["team"])
    accepted = [f for mid, f in findings.items() if score_eligible(state, mid, f)]
    total = profile["overall_score"]
    expected = len(state.get("team_plan", {}).get("selected_metric_ids", [])) \
        if state["team"].get("protocol") in {"leader-review-v1", "leader-review-v2"} else len(state["skills"]["metrics"])
    lines = [
        (
            f"本次为{ {'INITIAL': '初诊', 'FOLLOW_UP': '复诊', 'UNKNOWN': '初复诊未确定'}[state['context']['session_type']] }，"
            f"已提交 {sum(f.get('origin') != 'runtime_fallback' for f in findings.values())}/{expected} 项评价记录，"
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
    if not state["completion"]["complete"]:
        lines.append("团队执行或协作复核尚未完成；已展示的分数不代表团队复核已通过。")
    if state["team"].get("protocol") in {"leader-review-v1", "leader-review-v2"}:
        adjudicated = [mid for mid, f in findings.items() if f.get("decision_method") == "evidence_adjudicated"]
        lines.append(f"Leader选择{expected}项，已开展{state['team']['round']}轮反馈。")
        if adjudicated:
            lines.append("有据裁决（保留异议）：" + "、".join(adjudicated) + "；这些分数不代表全体一致。")
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
                "scoring_signature": r.get("quality_profile", {}).get("scoring_signature") if r else None,
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
        and previous.get("scoring_signature") == state["quality_profile"].get("scoring_signature")
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
    is_lead = team.get("protocol") in {"leader-review-v1", "leader-review-v2"}
    agent_results = []
    reasons = list(state["completion"]["issues"])
    tasks = ({"team_lead": {**team["tasks"]["team_lead"], "kind": "evaluator",
                           "findings": team["final_findings"]}} if is_lead else team["tasks"])
    for agent, task in tasks.items():
        if task["kind"] != "evaluator":
            continue
        output = []
        for mid, f in task["findings"].items():
            accepted = score_eligible(state, mid, f)
            outcome = finding_outcome(state, mid, f)
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
                    "outcome": outcome,
                    "failure_code": f.get("failure_code"),
                    "decision_method": f.get("decision_method"),
                }
            )
            if f["status"] == "NOT_EVALUABLE" and outcome != "configuration_blocked":
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
    required = len(state.get("team_plan", {}).get("selected_metric_ids", [])) if is_lead else len(metrics)
    if (required and len(state["completion"]["missing_metrics"]) == required) or (
        is_lead and not state.get("team_plan", {}).get("planning_complete")
    ):
        status = "failed"
    conflicts = list(team["conflicts"].values())
    report = {
        "evaluation_id": state["run_id"],
        "parent_evaluation_id": state.get("parent_evaluation_id"),
        "session_id": state["session"]["session_id"],
        "created_at": now(),
        "status": status,
        "schema_version": "3.0" if is_lead else "2.2",
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
        "score_notices": [
            f"{entry['metric_id']}: {entry['reason']}"
            for entry in state["quality_profile"].get("score_exclusions", [])
        ],
        "input_warnings": ([] if state["session"].get("observation_complete") else [
            "observation_completeness_unconfirmed"
        ]),
        "collaboration_complete": state["completion"]["complete"],
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
        # Guest workspaces are removed after the request; preserve safe field diagnostics
        # in the response without retaining/uploading the original dialogue or API keys.
        "execution_issues": [
            {"agent_id": e["actor"], "stage": e["detail"].get("purpose", "model"),
             "metric_id": e["detail"].get("metric_id"),
             "error": e["detail"].get("error") or e["detail"].get("code", "execution_error"),
             "fields": e["detail"].get("fields", []),
             "attempt": e["detail"].get("attempt"), "transport": e["detail"].get("transport")}
            for e in team["events"] if e["action"] in {"submission_rejected", "model_error"}
        ][-20:],
    }
    if is_lead:
        plan = state["team_plan"]
        adjudications = [f for f in team["final_findings"].values()
                        if f.get("decision_method") == "evidence_adjudicated"]
        if adjudications:
            report["arbitration_status"] = "resolved"
            report["arbitration_decisions"] = [
                {"conflict_id": "leader-decision-" + f["finding_id"], "metric_ids": [f["metric_id"]],
                 "status": "resolved", "rationale": f["reason"], "requires_manual_review": False}
                for f in adjudications]
        report["collaboration"] = {
            "protocol": team["protocol"], "prompt_version": team["prompt_version"],
            "selected_metric_ids": plan.get("selected_metric_ids", []),
            "excluded": plan.get("excluded", []), "weights": plan.get("weights", {}),
            "candidate_weights": plan.get("candidate_weights", {}),
            "weight_deviation": plan.get("weight_deviation", .2),
            "weight_policy": plan.get("weight_policy"),
            "weighting_stages": plan.get("weighting_stages", list(team.get("weighting_stages", {}).values())),
            "initial_metric_ids": plan.get("initial_metric_ids", []),
            "context_summary": plan.get("context_summary", ""), "round_count": team["round"],
            "score_gaps": team["score_gaps"],
            "initial_evaluations": [
                {"agent_id": agent, "perspective": team["tasks"][agent]["perspective"],
                 "findings": [{"metric_id": mid, "status": f["status"], "score": f["score"],
                               "reason": f["reason"], "evidence_ids": f["evidence_ids"]}
                              for mid, f in findings.items()]}
                for agent, findings in team["initial_evaluations"].items()],
            "reports": [{"version": r["version"], "round": r["round"], "final": r["final"],
                         "findings": [{"metric_id": mid, "score": item["finding"]["score"],
                                       "reason": item["finding"]["reason"], "question": item["question"],
                                       "decision_method": item["finding"].get("decision_method"),
                                       "responses": item["responses"]} for mid, item in r["items"].items()]}
                        for r in team["reports"]],
            "feedback": [f for by_agent in team["feedback"].values()
                         for items in by_agent.values() for f in items.values()],
        }
    return report
