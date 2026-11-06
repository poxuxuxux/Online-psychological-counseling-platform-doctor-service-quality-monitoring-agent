# 环节：评价工作流编排层；用途：定义评价阶段顺序、恢复和运行控制。
"""Deterministic outer StateGraph, dynamic inner StateGraph, durable node-boundary resume."""

import asyncio
import copy
import time
from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from app.context.service import SessionContextManager, build_history_context, preprocess
from app.domain.models import Session, uid
from app.evaluation.reporting import build_report, longitudinal, summarize
from app.evaluation.scoring import classify_risk, score
from app.infrastructure.repository import RunBusy
from app.infrastructure.telemetry import model_usage
from app.team.conflicts import finalize_conflicts, still_contradictory
from app.team.lead_protocol import (
    PROTOCOL,
    LeaderProtocol,
    complete_protocol,
    initialize_protocol,
    retry_protocol,
)
from app.team.post_initial_protocol import PROTOCOL_V2, PostInitialProtocol, initialize_post_initial
from app.team.runtime import GraphState, TeamRuntime
from app.team.state import active_findings, close_failed_inboxes, initialize_team
from app.team.tools import TeamTools

STAGES = [
    "preprocess",
    "session_context",
    "initial_context",
    "historical_context",
    "team_lead",
    "team_initialization",
    "team_runtime",
    "completion_check",
    "scoring_engine",
    "risk_classifier",
    "summary_generator",
    "longitudinal_analyzer",
    "report_builder",
    "evaluation_storage",
]


class EvaluationService:
    def __init__(self, settings, repository, model, catalog, knowledge):
        self.settings, self.repository, self.model = settings, repository, model
        self.catalog, self.knowledge = catalog, knowledge

    async def create(self, session: Session):
        normalized = preprocess(session)
        await self.repository.save_session(normalized)
        state = {
            "run_id": uid("eval"),
            "session": normalized,
            "skills": self.catalog.snapshot(),
            "status": "pending",
            "next_stage": "preprocess",
            "completed_stages": [],
            "dimension_ids": self.catalog.dimensions,
            "context": {},
            "elapsed_seconds": 0.0,
            "protocol": self.settings.team_protocol,
        }
        await self.repository.create_run(state)
        return state["run_id"]

    async def evaluate(self, session: Session):
        return await self.execute(await self.create(session))

    async def retry_incomplete(self, run_id):
        """Create a bounded continuation; never rewrite a finished report or reset its audit."""
        previous = await self.repository.get_run(run_id)
        if not previous or previous.get("next_stage") != "done":
            raise ValueError("Only a finished evaluation may be retried")
        if previous.get("completion", {}).get("complete"):
            raise ValueError("Execution already complete; material/review gaps require new evidence or review")
        new_id = uid("eval")
        if previous.get("protocol") in {PROTOCOL, PROTOCOL_V2}:
            state = retry_protocol(previous, new_id)
            await self.repository.create_run(state)
            return new_id
        state = {
            "run_id": new_id, "parent_evaluation_id": run_id,
            "session": copy.deepcopy(previous["session"]),
            "skills": copy.deepcopy(previous["skills"]),
            "dimension_ids": list(previous["dimension_ids"]),
            "context": copy.deepcopy(previous["context"]),
            "status": "pending", "next_stage": "team_runtime",
            "completed_stages": [s for s in previous["completed_stages"]
                                 if s in STAGES[:6]],
            "elapsed_seconds": 0.0,
        }
        team = state["team"] = initialize_team(state["skills"], new_id)
        old_team = previous["team"]
        team["evidence"] = copy.deepcopy(old_team["evidence"])
        team["risk_alerts"] = copy.deepcopy(old_team["risk_alerts"])
        retry_metrics = set(previous["completion"].get("missing_metrics", []))
        retry_metrics.update(mid for c in old_team["conflicts"].values()
                             if c["status"] != "RESOLVED" for mid in c["metric_ids"])
        team["conflict_reports"] = copy.deepcopy(old_team.get("conflict_reports", []))
        for c in old_team["conflicts"].values():
            if c["status"] != "RESOLVED":
                team["conflict_reports"].append({"metric_ids": c["metric_ids"],
                    "reason": c["description"], "reported_by": "retry_context"})
        for agent, current in team["tasks"].items():
            old = old_team["tasks"].get(agent, {})
            for mid, finding in old.get("findings", {}).items():
                if (mid in retry_metrics or mid in old.get("submission_errors", {})
                        or finding.get("origin") == "runtime_fallback"):
                    continue
                kept = copy.deepcopy(finding)
                kept.update(finding_id=uid("finding"), revision_count=0,
                            supersedes_finding_id=None, source_finding_id=finding["finding_id"])
                current["findings"][mid] = kept
                team["finding_history"].append(copy.deepcopy(kept))
            if set(current["findings"]) == set(current["metric_ids"]):
                current["status"] = "COMPLETED"
        # Pending peer requests must not silently disappear when retaining prior findings.
        from app.team.state import event
        for message in old_team["messages"]:
            if message["status"] != "PROCESSED" and message["receiver"] in team["tasks"]:
                copied = copy.deepcopy(message)
                copied.update(message_id=uid("msg"), evaluation_run_id=new_id, status="PENDING")
                team["messages"].append(copied)
                team["tasks"][copied["receiver"]]["status"] = "PENDING"
        event(team, "system", "retry_incomplete", {"parent_evaluation_id": run_id,
              "retained_metrics": sorted(active_findings(team))})
        await self.repository.create_run(state)
        return new_id

    async def execute(self, run_id):
        owner = uid("worker")
        if not await self.repository.claim(run_id, owner, self.settings.total_timeout + 120):
            raise RunBusy("run_busy_or_missing")
        start = time.monotonic()
        usage_token = None
        try:
            state = await self.repository.get_run(run_id)
            if state.get("report") and state["next_stage"] == "done":
                return state["report"]
            # 旧版本检查点可能停在已移除的独立校验节点。
            if state["next_stage"] == "evidence_validator":
                state["next_stage"] = "scoring_engine"
            previous_elapsed = state["elapsed_seconds"]
            usage_records = list(state.get("model_usage", []))
            usage_token = model_usage.set(usage_records)

            async def persist(data):
                data["elapsed_seconds"] = previous_elapsed + time.monotonic() - start
                data["model_usage"] = list(usage_records)
                await self.repository.checkpoint(data, owner)

            graph = self.build_graph(persist)
            graph_config = {
                "recursion_limit": self.settings.max_rounds * len(state["dimension_ids"]) * 6 + 100
            }
            remaining = self.settings.total_timeout - previous_elapsed
            try:
                if remaining <= 0:
                    raise TimeoutError
                result = await asyncio.wait_for(
                    graph.ainvoke({"data": state}, config=graph_config), remaining
                )
                return result["data"]["report"]
            except TimeoutError:
                # Finalize from the last durable state; do not run more model calls after timeout.
                state = await self.repository.get_run(run_id)
                if not state.get("context"):
                    state["context"] = build_history_context(
                        {
                            "session_type": "UNKNOWN",
                            "history": [],
                            "history_status": "unavailable",
                            "history_limit": 20,
                        }
                    )
                if "team" not in state:
                    initializer = initialize_post_initial if state.get("protocol") == PROTOCOL_V2 else initialize_protocol if state.get("protocol") == PROTOCOL else initialize_team
                    state["team"] = initializer(state["skills"], run_id)
                state["team"]["stop_reason"] = "total_timeout"
                state["next_stage"] = "completion_check"
                result = await graph.ainvoke({"data": state}, config=graph_config)
                return result["data"]["report"]
        finally:
            if usage_token is not None:
                model_usage.reset(usage_token)
            await self.repository.release(run_id, owner)

    def build_graph(self, persist):
        context_manager = SessionContextManager(self.repository)
        tools = TeamTools(self.settings, self.knowledge)
        runtime = TeamRuntime(self.settings, self.model, tools, persist)
        leader_runtime = LeaderProtocol(self.settings, self.model, self.knowledge, persist)
        post_initial_runtime = PostInitialProtocol(self.settings, self.model, self.knowledge, persist)
        graph = StateGraph(GraphState)

        async def process(name, state):
            data = state["data"]
            data["status"] = "running"
            if name == "preprocess":
                data["preprocessing"] = {
                    "text_messages": sum(
                        m["modality"] == "text" for m in data["session"]["messages"]
                    ),
                    "media_status": "text_only",
                    "notes": ["Non-text media requires upstream verified transcription"],
                }
                next_stage = "session_context"
            elif name == "session_context":
                data["context"] = await context_manager.route(data["session"])
                next_stage = (
                    "historical_context"
                    if data["context"]["session_type"] == "FOLLOW_UP"
                    else "initial_context"
                )
            elif name in {"initial_context", "historical_context"}:
                data["context"] = build_history_context(data["context"])
                next_stage = "team_lead"
            elif name == "team_lead":
                data["team_plan"] = {
                    "dimensions": data["dimension_ids"],
                    "required_metric_ids": list(data["skills"]["metrics"]) if data.get("protocol") not in {PROTOCOL, PROTOCOL_V2} else [],
                    "policy": data.get("protocol") if data.get("protocol") in {PROTOCOL, PROTOCOL_V2} else "owner_only_scoring_team_lead_arbitration",
                }
                next_stage = "team_initialization"
            elif name == "team_initialization":
                initializer = initialize_post_initial if data.get("protocol") == PROTOCOL_V2 else initialize_protocol if data.get("protocol") == PROTOCOL else initialize_team
                data["team"] = initializer(data["skills"], data["run_id"])
                next_stage = "team_runtime"
            elif name == "completion_check":
                if "team_runtime" not in data["completed_stages"]:
                    data["completed_stages"].append("team_runtime")
                if data.get("protocol") in {PROTOCOL, PROTOCOL_V2}:
                    complete_protocol(data)
                    data["completed_stages"].append(name)
                    data["next_stage"] = "scoring_engine"
                    await persist(data)
                    return {"data": data}
                finalize_conflicts(data["team"])
                # 失败任务的收件无法再被处理；超时恢复路径不再经过 schedule，这里兜底关闭。
                close_failed_inboxes(data["team"])
                findings = active_findings(data["team"])
                missing = sorted(set(data["skills"]["metrics"]) - set(findings))
                tasks_done = all(t["status"] == "COMPLETED" for t in data["team"]["tasks"].values())
                unread = [
                    m["message_id"] for m in data["team"]["messages"] if m["status"] != "PROCESSED"
                ]
                issues = ["missing_metrics:" + ",".join(missing)] if missing else []
                if not tasks_done:
                    issues.append("unfinished_agent_tasks")
                if unread:
                    issues.append("unprocessed_collaboration_messages")
                if data["team"]["stop_reason"] != "completed":
                    issues.append(data["team"]["stop_reason"] or "runtime_incomplete")
                data["completion"] = {
                    "complete": not issues,
                    # A failed optional lead pass must not erase independently accepted scores.
                    # Known/reported conflicts and unfinished evaluator collaboration still block.
                    "scoring_complete": (
                        not missing
                        and all(t["status"] == "COMPLETED" and not t.get("submission_errors")
                                for t in data["team"]["tasks"].values()
                                if t["kind"] == "evaluator")
                        and not unread
                        and not any(c["status"] != "RESOLVED"
                                    for c in data["team"]["conflicts"].values())
                        and not still_contradictory(data["team"], {"metric_ids": list(findings)})
                        and (not data["team"].get("conflict_reports")
                             or data["team"]["tasks"].get("team_lead", {}).get("phase") == "arbitrate")
                    ),
                    "issues": issues,
                    "missing_metrics": missing,
                    "unprocessed_messages": unread,
                }
                # Explicit per-metric null results for every uncovered required indicator.
                for agent, task in data["team"]["tasks"].items():
                    if task["kind"] != "evaluator":
                        continue
                    for mid in task["metric_ids"]:
                        if mid not in task["findings"]:
                            spec = data["skills"]["metrics"][mid]
                            task["findings"][mid] = {
                                "finding_id": uid("finding"),
                                "agent_id": agent,
                                "metric_id": mid,
                                "dimension_id": spec["dimension_id"],
                                "metric_version": spec["version"],
                                "status": "NOT_EVALUABLE",
                                "origin": "runtime_fallback",
                                "failure_code": task["error"] or data["team"]["stop_reason"]
                                or "evaluation_incomplete",
                                "score": None,
                                "reason": task["error"]
                                or data["team"]["stop_reason"]
                                or "未完成评价",
                                "evidence_ids": [],
                                "claims": [],
                                "review_rule_ids": [],
                                "risk": "none",
                                "revision_count": 0,
                                "supersedes_finding_id": None,
                            }
                next_stage = "scoring_engine"
            elif name == "scoring_engine":
                data["quality_profile"] = score(data)
                next_stage = "risk_classifier"
            elif name == "risk_classifier":
                data["risk"] = classify_risk(data)
                next_stage = "summary_generator"
            elif name == "summary_generator":
                data["summary"] = summarize(data)
                next_stage = "longitudinal_analyzer"
            elif name == "longitudinal_analyzer":
                data["longitudinal"] = longitudinal(data)
                next_stage = "report_builder"
            elif name == "report_builder":
                data["report"] = build_report(data)
                next_stage = "evaluation_storage"
            else:
                data["status"] = data["report"]["status"]
                next_stage = "done"
            if name not in data["completed_stages"]:
                data["completed_stages"].append(name)
            data["next_stage"] = next_stage
            await persist(data)
            return {"data": data}

        for name in STAGES:
            if name == "team_runtime":
                async def run_team(state):
                    selected_runtime = post_initial_runtime if state["data"].get("protocol") == PROTOCOL_V2 else leader_runtime if state["data"].get("protocol") == PROTOCOL else runtime
                    return await selected_runtime.graph.ainvoke(state)
                graph.add_node(name, run_team)
            else:

                async def node(state, stage=name):
                    return await process(stage, state)

                graph.add_node(name, node)
        graph.add_conditional_edges(
            START, lambda s: s["data"]["next_stage"], {stage: stage for stage in STAGES}
        )
        graph.add_edge("preprocess", "session_context")
        graph.add_conditional_edges(
            "session_context",
            lambda s: s["data"]["next_stage"],
            {"initial_context": "initial_context", "historical_context": "historical_context"},
        )
        graph.add_edge("initial_context", "team_lead")
        graph.add_edge("historical_context", "team_lead")
        for left, right in pairwise(STAGES[4:]):
            graph.add_edge(left, right)
        graph.add_edge("evaluation_storage", END)
        return graph.compile(name="doctor_service_evaluation")
