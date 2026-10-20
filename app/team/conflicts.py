# 环节：Agent 团队运行层；用途：管理团队循环、任务状态、共享证据、消息或工具。
"""Fact conflicts only. Score differences across dimensions are not conflicts."""

from itertools import combinations

from app.domain.models import uid
from app.team.state import active_findings


def detect_fact_conflicts(team):
    findings = active_findings(team)
    known = {c["signature"] for c in team["conflicts"].values()}
    for left, right in combinations(findings.values(), 2):
        for a in left["claims"]:
            for b in right["claims"]:
                key = (a["subject"], a["behavior"].strip().casefold(), a["scope"].strip())
                other = (b["subject"], b["behavior"].strip().casefold(), b["scope"].strip())
                if key != other or a["polarity"] == b["polarity"]:
                    continue
                signature = "|".join(sorted([left["metric_id"], right["metric_id"]]) + list(key))
                if signature in known:
                    continue
                conflict = {
                    "conflict_id": uid("conflict"),
                    "signature": signature,
                    "metric_ids": [left["metric_id"], right["metric_id"]],
                    "description": "Same subject, behavior and scope with opposite assertions",
                    "status": "OPEN",
                    "review": None,
                    "kind": "fact_contradiction",
                    "finding_ids": [left["finding_id"], right["finding_id"]],
                }
                team["conflicts"][conflict["conflict_id"]] = conflict
                known.add(signature)


def still_contradictory(team, conflict):
    findings = active_findings(team)
    for left, right in combinations(
        [findings[m] for m in conflict["metric_ids"] if m in findings], 2
    ):
        for a in left["claims"]:
            for b in right["claims"]:
                if (a["subject"], a["behavior"].strip().casefold(), a["scope"].strip()) == (
                    b["subject"],
                    b["behavior"].strip().casefold(),
                    b["scope"].strip(),
                ) and a["polarity"] != b["polarity"]:
                    return True
    return False


def finalize_conflicts(team):
    """在团队结束时按复核决定和最终事实声明收敛冲突状态。"""
    findings = active_findings(team)
    for conflict in team["conflicts"].values():
        review = conflict.get("review")
        revised = all(
            mid in findings and findings[mid]["finding_id"] not in conflict["finding_ids"]
            for mid in conflict["metric_ids"]
        )
        resolved = bool(
            review
            and review["decision"] != "unresolved"
            and (review["decision"] == "uphold" or revised)
            and all(mid in findings for mid in conflict["metric_ids"])
            and not still_contradictory(team, conflict)
        )
        conflict["status"] = "RESOLVED" if resolved else "UNRESOLVED"
