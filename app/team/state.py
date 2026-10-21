# 环节：Agent 团队运行层；用途：管理团队循环、任务状态、共享证据、消息或工具。
from app.domain.models import now, uid
from app.rubrics.groups import evaluator_groups


def event(team, actor, action, detail):
    team["events"].append(
        {
            "event_id": uid("event"),
            "created_at": now(),
            "actor": actor,
            "action": action,
            "detail": detail,
        }
    )


def task(agent, dimension, metrics, kind="evaluator", conflict_id=None):
    return {
        "task_id": uid("task"),
        "assigned_agent": agent,
        "dimension_id": dimension,
        "kind": kind,
        "metric_ids": metrics,
        "status": "PENDING",
        "steps": 0,
        "model_seconds": 0.0,
        "created_at": now(),
        "updated_at": now(),
        "findings": {},
        "revisions": {},
        "observations": [],
        "skills_read": False,
        "conflict_id": conflict_id,
        "error": None,
    }


def initialize_team(skills, run_id):
    tasks = {}
    for group in evaluator_groups(skills["metrics"]):
        dimension = group["lead_dimension"]
        dimensions = group["dimension_ids"]
        agent = "evaluator:" + dimension
        tasks[agent] = task(
            agent,
            dimension,
            [mid for mid, spec in skills["metrics"].items() if spec["dimension_id"] in dimensions],
        )
        tasks[agent]["group_id"] = group["group_id"]
        tasks[agent]["dimension_ids"] = dimensions
        tasks[agent]["evaluation_run_id"] = run_id
    return {
        "tasks": tasks,
        "evidence": {},
        "messages": [],
        "events": [],
        "conflicts": {},
        "conflict_reports": [],
        "risk_alerts": [],
        "finding_history": [],
        "turn": 0,
        "cursor": 0,
        "active_agent": None,
        "active_agents": [],
        "observations": None,
        "decisions": None,
        "stop_reason": None,
        "model_calls": 0,
        "reviews_created": 0,
        "decision": None,
    }


def active_findings(team):
    return {
        mid: f
        for t in team["tasks"].values()
        if t["kind"] == "evaluator"
        for mid, f in t["findings"].items()
    }


def pending_messages(team, receiver):
    return [
        m
        for m in team["messages"]
        if m["receiver"] == receiver and m["status"] in {"PENDING", "DELIVERED"}
    ]
