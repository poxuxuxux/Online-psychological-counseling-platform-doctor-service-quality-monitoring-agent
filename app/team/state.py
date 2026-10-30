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
    if team.get("protocol") in {"leader-review-v1", "leader-review-v2"}:
        return dict(team.get("final_findings", {}))
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


def close_inbox(team, agent, reason):
    """系统关闭无法再被代理处理的收件消息，避免失败/超预算任务的孤儿消息阻塞完成门控。"""
    closed = []
    for message in team["messages"]:
        if message["receiver"] == agent and message["status"] in {"PENDING", "DELIVERED"}:
            message.update(
                status="PROCESSED",
                disposition="system_closed",
                processing_reason=reason,
                processed_at=now(),
            )
            closed.append(message["message_id"])
    if closed:
        event(
            team,
            "system",
            "close_inbox",
            {"receiver": agent, "message_ids": closed, "reason": reason},
        )
    return closed


def close_failed_inboxes(team):
    for agent, current in team["tasks"].items():
        if current["status"] == "FAILED":
            close_inbox(team, agent, "receiver_agent_failed")
