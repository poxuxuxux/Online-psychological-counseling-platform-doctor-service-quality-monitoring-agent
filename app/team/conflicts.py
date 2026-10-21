# 环节：Agent 团队运行层；用途：管理团队循环、任务状态、共享证据、消息或工具。
"""Post-arbitration consistency check for conflicts identified by Team Lead."""

from itertools import combinations

from app.team.state import active_findings


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
