# 环节：Leader中心化协商；用途：冻结选项和权重、独立初评、三轮报告反馈及有据裁决。
"""Explicit LangGraph phases. Legacy checkpoints continue to use the original runtime."""
import asyncio
import copy
import json
from collections import Counter
from dataclasses import replace

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.domain.models import FindingInput, now, uid
from app.domain.ports import ModelUnavailable
from app.infrastructure.telemetry import model_usage
from app.rubrics.payload import metric_payload
from app.team.message_bus import LEADER, MessageBus
from app.team.prompts import (
    EVALUATOR_FEEDBACK,
    EVALUATOR_INITIAL,
    LEADER_FINAL,
    LEADER_PLAN,
    LEADER_REPORT,
    LEADER_REVISION,
    PROMPT_VERSION,
)
from app.team.protocol_models import (
    Feedback,
    FeedbackBatch,
    InitialBatch,
    LeaderItem,
    Plan,
    leader_batch_schema,
)
from app.team.runtime import GraphState
from app.team.state import close_inbox, event, initialize_team, task
from app.team.tools import TeamTools
from app.team.weights import bounded_weights

PROTOCOL = "leader-review-v1"
PERSPECTIVES = {
    "evaluator:effectiveness": "关键问题解决与服务实效：核对患者核心诉求、有效回应和必要专业边界。",
    "evaluator:empathy": "情绪处境与沟通细节：核对情绪理解、语境贴合、尊重及非评判性。",
    "evaluator:collaboration": "响应协作与建议落地：核对可靠计时、共同决策、个体化和可执行性。",
}


class ProtocolStop(RuntimeError):
    pass


def initialize_protocol(skills, run_id):
    team = initialize_team(skills, run_id)
    team.update(protocol=PROTOCOL, run_id=run_id, phase="planning", round=0,
                reports=[], feedback={}, final_findings={}, draft={}, initial_evaluations={},
                prompt_version=PROMPT_VERSION, request_markers={}, score_gaps={})
    team["tasks"] = {LEADER: task(LEADER, "leadership", [], "team_lead")}
    for agent, perspective in PERSPECTIVES.items():
        team["tasks"][agent] = task(agent, "all_selected", [])
        team["tasks"][agent]["perspective"] = perspective
    for current in team["tasks"].values():
        current["evaluation_run_id"] = run_id
    return team


def complete_protocol(data):
    """Keep execution gaps distinct from genuine source gaps; never invent a selection."""
    team = data["team"]
    selected = data.get("team_plan", {}).get("selected_metric_ids", [])
    missing = sorted(set(selected) - set(team["final_findings"]))
    unread = [m["message_id"] for m in team["messages"] if m["status"] != "PROCESSED"]
    issues = []
    if team.get("stop_reason") != "completed":
        issues.append(team.get("stop_reason") or "evaluation_incomplete")
    if not data.get("team_plan", {}).get("planning_complete"):
        issues.append("leader_planning_incomplete")
    if missing:
        issues.append("missing_metrics:" + ",".join(missing))
    if unread:
        issues.append("unprocessed_collaboration_messages")
    for mid in missing:
        spec = data["skills"]["metrics"][mid]
        team["final_findings"][mid] = {
            "finding_id": uid("finding"), "metric_id": mid, "agent_id": LEADER,
            "dimension_id": spec["dimension_id"], "metric_version": spec["version"],
            "status": "NOT_EVALUABLE", "score": None,
            "reason": team.get("stop_reason") or "evaluation_incomplete",
            "evidence_ids": [], "claims": [], "review_rule_ids": [], "risk": "none",
            "revision_count": 0, "supersedes_finding_id": None,
            "origin": "runtime_fallback", "failure_code": team.get("stop_reason"),
            "decision_method": "execution_failed",
        }
    for agent in team["tasks"]:
        close_inbox(team, agent, "run_finalized_before_receiver_finished")
    data["completion"] = {"complete": not issues, "scoring_complete": not issues,
                          "issues": issues, "missing_metrics": missing,
                          "unprocessed_messages": unread}


def retry_protocol(previous, new_id):
    state = copy.deepcopy(previous)
    for key in ("report", "completion", "quality_profile", "risk", "summary", "longitudinal", "model_usage"):
        state.pop(key, None)
    state.update(run_id=new_id, parent_evaluation_id=previous["run_id"], status="pending",
                 next_stage="team_runtime", elapsed_seconds=0.0)
    state["completed_stages"] = [s for s in previous["completed_stages"]
                                 if s not in {"team_runtime", "completion_check", "scoring_engine",
                                              "risk_classifier", "summary_generator",
                                              "longitudinal_analyzer", "report_builder", "evaluation_storage"}]
    team = state["team"]
    phase = team.get("resume_phase", team["phase"])
    if phase == "done":
        raise ValueError("No unfinished protocol phase remains")
    team.update(run_id=new_id, phase=phase, stop_reason=None, model_calls=0, turn=0, reserved_input_characters=0)
    team["request_markers"] = {}
    team["final_findings"] = {mid: f for mid, f in team["final_findings"].items()
                              if f.get("origin") != "runtime_fallback"}
    for current in team["tasks"].values():
        current.update(evaluation_run_id=new_id, steps=0, model_seconds=0.0, error=None,
                       consecutive_model_errors=0, phase_steps={}, validation_attempts={}, last_errors={})
        if current["status"] == "FAILED":
            current["status"] = "PENDING"
    event(team, "system", "retry_incomplete", {"parent_evaluation_id": previous["run_id"],
          "resume_phase": phase})
    return state


class LeaderProtocol:
    def __init__(self, settings, model, knowledge, persist):
        self.settings, self.model, self.persist = settings, model, persist
        self.tools = TeamTools(replace(settings, max_revisions=3), knowledge)
        graph = StateGraph(GraphState)
        graph.add_node("advance", self.advance)
        graph.add_node("save", self.save)
        graph.add_edge(START, "advance")
        graph.add_edge("advance", "save")
        graph.add_conditional_edges("save", lambda s: s["data"]["team"]["phase"] == "done",
                                    {True: END, False: "advance"})
        self.graph = graph.compile(name="leader_centered_three_round_review")

    async def save(self, state):
        await self.persist(state["data"])
        return state

    def _bus(self, data):
        return MessageBus(data["team"], self.settings.max_messages)

    def _abort(self, data, reason):
        team = data["team"]
        team["resume_phase"] = team["phase"]
        team.update(phase="done", stop_reason=reason)
        for agent, current in team["tasks"].items():
            if current["status"] != "COMPLETED":
                current.update(status="FAILED", error=current.get("error") or reason)
            close_inbox(team, agent, "execution_incomplete")
        event(team, "system", "protocol_stopped", {"reason": reason})

    async def advance(self, state):
        data = state["data"]
        try:
            if not self.model.configured:
                raise ProtocolStop("model_not_configured")
            await getattr(self, "_" + data["team"]["phase"])(data)
        except ProtocolStop as error:
            self._abort(data, str(error))
        except ValueError as error:
            if str(error) == "message_budget_exhausted":
                self._abort(data, str(error))
            else:
                raise
        return {"data": data}

    def _base(self, data, agent, purpose, requested):
        current = data["team"]["tasks"][agent]
        evidence = data["team"]["evidence"]
        annotated_dialogue = {**data["session"], "messages": [
            {**message, "evidence_id": ("e-" + message["message_id"])
             if "e-" + message["message_id"] in evidence else None}
            for message in data["session"]["messages"]
        ]}
        metrics = {}
        for mid in requested:
            spec = metric_payload(data["skills"]["metrics"][mid])
            # Transport instructions are versioned centrally, not copied from legacy Skill tails.
            spec["instructions"] = spec["instructions"].split("## 执行与接口约定")[0]
            metrics[mid] = spec
        return {
            "purpose": purpose, "task": {"assigned_agent": agent, "kind": current["kind"]},
            "perspective": current.get("perspective"), "dialogue": annotated_dialogue,
            "available_evidence_ids": list(evidence)[:50],
            "evidence_reference_rule": (
                "Copy each message's non-null evidence_id exactly into finding and claim evidence_ids. "
                "Do not invent, rename, or use message_id instead. Registry preview may be truncated; "
                "each dialogue message contains its complete exact evidence_id."
            ),
            "session_context": {k: data["context"].get(k) for k in ("session_type", "history_status")},
            "frozen_skills": metrics, "requested_metric_ids": requested,
            "weights": data.get("team_plan", {}).get("weights", {}),
            "last_errors": current.get("last_errors", {}),
            "time_facts": current.get("time_facts", {}),
            "finding_schema": FindingInput.model_json_schema(),
        }

    async def _ask(self, data, requests):
        team = data["team"]
        usage = model_usage.get() or []
        if sum(r.get("input_characters", 0) for r in usage) >= self.settings.max_input_chars:
            raise ProtocolStop("input_budget_exhausted")
        available = self.settings.max_model_calls - team["model_calls"]
        if available <= 0:
            raise ProtocolStop("model_call_budget_exhausted")
        requests = requests[:min(self.settings.concurrency, available)]
        usable = []
        reserved = max(team.get("reserved_input_characters", 0),
                       sum(r.get("input_characters", 0) for r in usage))
        for agent, purpose, system, payload, schema in requests:
            if "report_version" in payload:
                # Versions belong to the workflow, not the model. Bind each request
                # without mutating the shared schema or accepting stale responses.
                version = payload["report_version"]
                schema = copy.deepcopy(schema)
                schema["properties"]["report_version"].update(
                    const=version, enum=[version],
                    description=f"Copy payload.report_version exactly: {version}",
                )
                system += (
                    f"\n本次输出顶层report_version必须为整数{version}，原样复制payload.report_version。"
                    "这是程序指定的目标版本号，不是轮次、批次数或需要你递增的计数。"
                    "初步报告P0使用0；修订/裁决的目标版本也已由程序计算。"
                    "current_report可能是上一版供你修订，不能抄它的旧版本或自行再加1。"
                    "评价反馈必须绑定所审阅报告的指定版本。"
                )
            current = team["tasks"][agent]
            steps = current.setdefault("phase_steps", {})
            step_key = f"{purpose}:v{payload['report_version']}" if "report_version" in payload else purpose
            if (steps.get(step_key, 0) >= self.settings.max_steps
                    or current["model_seconds"] >= self.settings.agent_timeout):
                current.update(status="FAILED", error="agent_budget_exhausted")
                continue
            estimate = (len(system) + len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                        + len(json.dumps(schema, ensure_ascii=False, separators=(",", ":"))) + 64)
            if reserved + estimate > self.settings.max_input_chars:
                if not usable:
                    raise ProtocolStop("input_budget_exhausted")
                break
            reserved += estimate
            steps[step_key] = steps.get(step_key, 0) + 1
            current["steps"] += 1
            usable.append((agent, purpose, system, payload, schema))
        team["model_calls"] += len(usable)
        team["reserved_input_characters"] = reserved
        team["turn"] += len(usable)
        await self.persist(data)  # Reserve calls before the network, including on crash recovery.

        async def call(request):
            import time
            agent, purpose, system, payload, schema = request
            current = team["tasks"][agent]
            start = time.monotonic()
            diagnostics = None
            try:
                timeout = min(self.settings.model_timeout,
                              self.settings.agent_timeout - current["model_seconds"])
                result = await asyncio.wait_for(self.model.json(system, payload, schema), timeout)
                current["consecutive_model_errors"] = 0
                current.setdefault("last_errors", {}).pop(purpose, None)
                return agent, payload, result
            except TimeoutError:
                error = "model_timeout"
            except ModelUnavailable as exc:
                error = str(exc)
                diagnostics = getattr(exc, "diagnostics", None)
            except Exception:  # noqa: BLE001 - isolate provider adapters behind a stable error code
                error = "model_or_schema_error"
            finally:
                current["model_seconds"] += time.monotonic() - start
            count = current.get("consecutive_model_errors", 0) + 1
            current["consecutive_model_errors"] = count
            current.setdefault("last_errors", {})[purpose] = {"error": error, "transport": diagnostics}
            formatted = error in {"model_truncated_response", "model_invalid_json", "model_schema_error"}
            if formatted:
                current["batch_size"] = 1
            if count >= (3 if formatted else 2):
                current.update(status="FAILED", error=error)
            event(team, agent, "model_error", {"code": error, "purpose": purpose, "transport": diagnostics})
            return agent, payload, None

        return await asyncio.gather(*(call(r) for r in usable))

    def _error(self, data, agent, purpose, mid, error):
        current = data["team"]["tasks"][agent]
        fields = [{"path": list(e["loc"]), "type": e["type"]} for e in error.errors()] \
            if isinstance(error, ValidationError) else []
        detail = {"error": str(error)[:450] if not fields else "schema_error", "fields": fields}
        key = purpose + ":" + str(mid)
        attempts = current.setdefault("validation_attempts", {})
        attempts[key] = attempts.get(key, 0) + 1
        current.setdefault("last_errors", {})[str(mid)] = detail
        current["batch_size"] = 1
        if attempts[key] >= 3:
            current.update(status="FAILED", error="metric_submission_rejected")
        event(data["team"], agent, "submission_rejected", {"metric_id": mid, "purpose": purpose,
              "attempt": attempts[key], **detail})

    def _consume(self, data, agent, purpose, raw, field, requested, parser, version=None):
        if raw is None:
            return
        try:
            if not isinstance(raw, dict) or not isinstance(raw.get(field), list):
                raise TypeError("Response must contain " + field + " array")
            if version is not None and (type(raw.get("report_version")) is not int
                                        or raw["report_version"] != version):
                raise ValueError(f"stale_or_incorrect_report_version: expected {version}, "
                                 f"received {raw.get('report_version')!r}")
            items = raw[field]
            def mid_of(item):
                if not isinstance(item, dict):
                    return None
                if field == "items":
                    nested = item.get("finding")
                    return nested.get("metric_id") if isinstance(nested, dict) else None
                return item.get("metric_id")
            ids = [mid_of(item) for item in items]
            counts = Counter(str(mid) for mid in ids)
            # Foreign or duplicate results are not permitted to mutate accepted siblings.
            for mid in requested:
                try:
                    if counts[str(mid)] != 1:
                        raise ValueError("Exactly one result per requested metric is required")
                    item = items[ids.index(mid)]
                    parser(mid, item)
                    data["team"]["tasks"][agent].setdefault("last_errors", {}).pop(mid, None)
                except (ValueError, TypeError, KeyError) as error:
                    self._error(data, agent, purpose, mid, error)
            if any(mid not in requested for mid in ids):
                event(data["team"], agent, "unrequested_results_ignored", {"purpose": purpose})
        except (ValueError, TypeError, KeyError) as error:
            for mid in requested:
                self._error(data, agent, purpose, mid, error)

    def _check_failed(self, data):
        failed = [t for t in data["team"]["tasks"].values() if t["status"] == "FAILED"]
        if failed:
            raise ProtocolStop(failed[0]["error"] or "execution_incomplete")

    def _drain(self, data, receiver, reason):
        bus = self._bus(data)
        received = bus.check_inbox(receiver)
        bus.acknowledge(receiver, [m["message_id"] for m in received], reason)

    def _send_once(self, data, key, sender, receiver, kind, payload, **metadata):
        if key not in data["team"]["request_markers"]:
            mid = self._bus(data).send_message(sender, receiver, kind, payload, **metadata)
            data["team"]["request_markers"][key] = mid

    async def _planning(self, data):
        metrics = data["skills"]["metrics"]
        payload = self._base(data, LEADER, "leader_plan", list(metrics))
        payload["weight_deviation"] = self.settings.weight_deviation
        results = await self._ask(data, [(LEADER, "leader_plan", LEADER_PLAN, payload, Plan.model_json_schema())])
        for agent, _, raw in results:
            if raw is None:
                continue
            try:
                plan = Plan.model_validate(raw)
                ids = [item.metric_id for item in plan.selected + plan.excluded]
                if len(ids) != len(set(ids)) or set(ids) != set(metrics):
                    raise ValueError("Every catalog metric must occur once in selected or excluded")
                proposed = {item.metric_id: item.candidate_weight for item in plan.selected}
                fallback = bool(proposed) and not any(proposed.values())
                weights = bounded_weights(dict.fromkeys(proposed, 1.0) if fallback else proposed,
                                          self.settings.weight_deviation)
                data["team_plan"] = {**plan.model_dump(), "planning_complete": True,
                    "selected_metric_ids": list(proposed), "candidate_weights": proposed,
                    "weights": weights, "weight_deviation": self.settings.weight_deviation,
                    "weight_fallback": "zero_candidates_equal_weights" if fallback else None,
                    "policy": PROTOCOL, "weight_policy": "bounded-equal-simplex-v1"}
                team = data["team"]
                for current in team["tasks"].values():
                    current.update(metric_ids=list(proposed), skills_read=True,
                                   time_facts=self.tools.time_facts(data["session"]))
                # Every supported text message gets its immutable source reference.
                for message in data["session"]["messages"]:
                    if (message["message_kind"] == "dialogue" and message["modality"] == "text"
                            and message["role"] in {"doctor", "patient"} and message["content"].strip()):
                        eid = "e-" + message["message_id"]
                        team["evidence"][eid] = {"evidence_id": eid, "session_id": data["session"]["session_id"],
                            "message_id": message["message_id"], "turn_id": message["sequence"],
                            "speaker": message["role"], "original_text": message["content"],
                            "source_agent": "context_manager", "related_indicators": [], "created_at": now()}
                event(team, LEADER, "plan_frozen", copy.deepcopy(data["team_plan"]))
                for teammate in PERSPECTIVES:
                    self._send_once(data, "task:" + teammate, LEADER, teammate, "TASK_ASSIGNMENT",
                                    data["team_plan"])
                team["phase"] = "initial"
            except (ValueError, TypeError, KeyError) as error:
                self._error(data, agent, "leader_plan", "plan", error)
        self._check_failed(data)

    async def _initial(self, data):
        team = data["team"]
        requests = []
        for agent in PERSPECTIVES:
            current = team["tasks"][agent]
            todo = [mid for mid in current["metric_ids"] if mid not in current["findings"]]
            if not todo:
                current["status"] = "COMPLETED"
                if agent not in team["initial_evaluations"]:
                    team["initial_evaluations"][agent] = copy.deepcopy(current["findings"])
                    self._drain(data, agent, "independent_initial_evaluation_submitted")
                    self._send_once(data, "initial:" + agent, agent, LEADER, "INITIAL_EVALUATION",
                                    current["findings"])
                continue
            self._bus(data).check_inbox(agent)
            requested = todo[:current.get("batch_size", 2)]
            payload = self._base(data, agent, "initial_evaluation", requested)
            payload["own_accepted_findings"] = current["findings"]
            requests.append((agent, "initial_evaluation", EVALUATOR_INITIAL, payload,
                             InitialBatch.model_json_schema()))
        for agent, payload, raw in await self._ask(data, requests) if requests else []:
            def accept(mid, item, owner=agent):
                FindingInput.model_validate(item)
                result = self.tools.submit(data, owner, {"findings": [item]})
                if result["rejected"]:
                    raise ValueError(result["rejected"][0]["error"])
            self._consume(data, agent, "initial_evaluation", raw, "findings",
                          payload["requested_metric_ids"], accept)
        self._check_failed(data)
        if all(agent in team["initial_evaluations"] for agent in PERSPECTIVES):
            self._drain(data, LEADER, "all_independent_evaluations_received")
            team["score_gaps"] = self._gaps(data)
            team["initial_score_gaps"] = copy.deepcopy(team["score_gaps"])
            team["phase"] = "report"

    def _gaps(self, data):
        result = {}
        for mid in data["team_plan"]["selected_metric_ids"]:
            team = data["team"]
            scores = []
            for agent in PERSPECTIVES:
                current = team["feedback"].get(str(team["round"]), {}).get(agent, {}).get(mid)
                if current and current["decision"] == "agree" and team["reports"]:
                    value = team["reports"][-1]["items"][mid]["finding"]["score"]
                elif current and current["decision"] == "insufficient":
                    value = None
                else:
                    value = team["tasks"][agent]["findings"][mid]["score"]
                scores.append(value)
            gap = max(scores) - min(scores) if all(s is not None for s in scores) else None
            result[mid] = {"scores": scores, "gap": gap, "large_gap": gap is not None and gap >= 3,
                           "non_numeric_review": gap is None}
        return result

    def _validated_candidate(self, data, mid, finding):
        f = FindingInput.model_validate(finding)
        if f.metric_id != mid:
            raise ValueError("Mismatched finding metric")
        if f.status == "NOT_APPLICABLE" and not data["session"]["observation_complete"]:
            raise ValueError("Not-applicable conclusion needs confirmed complete observation")
        original = data["team"]
        scratch_task = {**original["tasks"][LEADER], "kind": "evaluator", "findings": {},
                        "submission_errors": {}}
        scratch = {"tasks": {LEADER: scratch_task}, "evidence": original["evidence"],
                   "finding_history": [], "risk_alerts": [], "conflicts": {}}
        result = self.tools.submit({**data, "team": scratch}, LEADER, {"findings": [f.model_dump()]})
        if result["rejected"]:
            raise ValueError(result["rejected"][0]["error"])
        return scratch_task["findings"][mid]

    def _round_feedback(self, data, mid):
        return [items[mid] for items in data["team"]["feedback"].get(str(data["team"]["round"]), {}).values()
                if mid in items]

    def _agreed(self, data, mid):
        reports = data["team"]["reports"]
        if reports:
            candidate = reports[-1]["items"][mid]
            if (candidate["factual_resolution"] == "unresolved"
                    and candidate["finding"]["status"] != "NOT_EVALUABLE"):
                return False  # A provisional contradiction cannot become a canonical consensus.
        feedback = self._round_feedback(data, mid)
        return len(feedback) == 3 and all(f["decision"] == "agree" and f["issue_type"] == "none" for f in feedback)

    async def _report(self, data):
        await self._leader_batch(data, final=False, initial=True)

    async def _revision(self, data):
        team = data["team"]
        selected = data["team_plan"]["selected_metric_ids"]
        if all(self._agreed(data, mid) for mid in selected):
            report = team["reports"][-1]
            for mid, item in report["items"].items():
                f = copy.deepcopy(item["finding"])
                f["decision_method"] = "consensus"
                f["report_version"] = report["version"]
                team["final_findings"][mid] = f
            self._finish(data)
            return
        await self._leader_batch(data, final=team["round"] >= 3, initial=False)

    async def _leader_batch(self, data, *, final, initial):
        team = data["team"]
        version = 0 if initial else team["reports"][-1]["version"] + 1
        purpose = "leader_preliminary" if initial else "leader_final" if final else "leader_revision"
        current = team["tasks"][LEADER]
        todo = [mid for mid in data["team_plan"]["selected_metric_ids"] if mid not in team["draft"]]
        if todo:
            requested = todo[:current.get("batch_size", 2)]
            payload = self._base(data, LEADER, purpose, requested)
            payload.update(report_version=version, round=team["round"], report_is_final=final,
                           score_gaps={mid: team["score_gaps"][mid] for mid in requested},
                           initial_evaluations={a: {mid: fs[mid] for mid in requested}
                                                for a, fs in team["initial_evaluations"].items()},
                           current_report=team["reports"][-1] if team["reports"] else None,
                           received_feedback={mid: self._round_feedback(data, mid) for mid in requested})
            if payload["current_report"]:
                payload["current_report"] = {**payload["current_report"], "items": {
                    mid: payload["current_report"]["items"][mid] for mid in requested}}
            prompt = LEADER_REPORT if initial else LEADER_FINAL if final else LEADER_REVISION
            if not final:
                prompt += (
                    "\n本次是非终评报告，items中每一项decision_method必须且只能为provisional。"
                    "这与finding.status是两个独立字段：即使status=NOT_EVALUABLE或NOT_APPLICABLE、"
                    "score=null，本项decision_method仍须为provisional。"
                    "不得提前使用not_evaluable、not_applicable、consensus或evidence_adjudicated。"
                )
            schema = leader_batch_schema(final=final)
            for agent, _, raw in await self._ask(data, [(LEADER, purpose, prompt, payload, schema)]):
                def accept(mid, value):
                    # A missing discussion question is presentation metadata, not a
                    # reason to discard otherwise valid evidence and scoring.
                    defaulted_question = False
                    if isinstance(value, dict) and (
                        value.get("question") is None
                        or isinstance(value.get("question"), str) and not value["question"].strip()
                    ):
                        value = copy.deepcopy(value)
                        if final:
                            question = "【程序补充】本项已进入最终裁决，请保留裁决理由与异议记录，不再开启新一轮协商。"
                        else:
                            scores = {a: fs[mid].get("score") for a, fs in team["initial_evaluations"].items()}
                            question = (f"【程序补充】请核对指标{mid}的原文证据、适用条件与评分锚点，"
                                        "逐项审阅Leader当前理由；不同意时请给出可定位反证或缺失信息。")
                            if team["score_gaps"].get(mid, {}).get("large_gap"):
                                question += f"当前记录有大分差，三方初评分为{scores}，请说明分差涉及的事实或锚点依据。"
                            if value.get("factual_resolution") == "unresolved":
                                question += "关键事实或适用性尚未确认，请说明哪些原文可以确认或仍缺少什么，确认前不强行给分。"
                        value["question"] = question
                        defaulted_question = True
                    item = LeaderItem.model_validate(value)
                    f = self._validated_candidate(data, mid, item.finding.model_dump())
                    pending_facts = f["status"] != "NOT_EVALUABLE" and item.factual_resolution != "resolved"
                    if pending_facts and final:
                        raise ValueError(
                            "Unresolved facts/applicability need NOT_EVALUABLE, not a score or exclusion; "
                            f"received factual_resolution={item.factual_resolution!r}, "
                            f"status={f['status']!r}, score={f['score']!r}. "
                            "Recheck evidence: if facts/applicability are unknown use NOT_EVALUABLE/score=null; "
                            "if grounded use resolved. Pending discussion alone does not mean unresolved."
                        )
                    expected = {fb["feedback_id"]: fb for fb in self._round_feedback(data, mid)} if not initial else {}
                    if (len(item.responses) != len(expected)
                            or {r.feedback_id for r in item.responses} != set(expected)):
                        raise ValueError("Respond exactly once to EVERY feedback_id for this metric")
                    for response in item.responses:
                        self.tools.check_evidence(team, response.evidence_ids)
                        if (response.disposition != "accepted" and expected[response.feedback_id]["decision"] != "agree"
                                and not response.evidence_ids):
                            raise ValueError("Rejecting an objection needs original evidence and reason")
                    if final:
                        previous = team["reports"][-1]["items"][mid]["finding"]
                        same = (f["status"], f["score"]) == (previous["status"], previous["score"])
                        if item.decision_method == "consensus" and not (self._agreed(data, mid) and same):
                            raise ValueError("Consensus requires all three to agree with this exact version/result")
                        if f["status"] == "EVALUATED" and item.decision_method not in {"consensus", "evidence_adjudicated"}:
                            raise ValueError("Final numeric score must be consensus or evidence_adjudicated")
                        if f["status"] == "NOT_EVALUABLE" and item.decision_method not in {"not_evaluable", "consensus"}:
                            raise ValueError("Unscored final results must be not_evaluable or genuine consensus")
                        if f["status"] == "NOT_APPLICABLE" and item.decision_method not in {"not_applicable", "consensus"}:
                            raise ValueError("An excluded final result must be not_applicable or genuine consensus")
                    elif item.decision_method != "provisional":
                        raise ValueError("Nonfinal reports must be provisional: "
                                         f"expected decision_method='provisional', received {item.decision_method!r}; "
                                         "keep finding.status/score as supported by evidence")
                    prior = team["reports"][-1]["items"][mid]["finding"] if team["reports"] else None
                    f.update(revision_count=version, supersedes_finding_id=prior["finding_id"] if prior else None,
                             decision_method=item.decision_method, report_version=version)
                    stored = {**item.model_dump(), "finding": f}
                    if pending_facts:
                        stored["question"] = (
                            "【待核对候选，不作为终评分】Leader同时提交了未确认事实与候选评分/不适用判断。"
                            "请核对原文、触发条件和锚点，说明是否能确认关键事实；无法确认时请指出缺口。"
                            + stored["question"]
                        )[:2000]
                    team["draft"][mid] = stored
                    if pending_facts:
                        event(team, LEADER, "provisional_facts_pending",
                              {"metric_id": mid, "report_version": version, "candidate_status": f["status"],
                               "candidate_score": f["score"]})
                    if defaulted_question:
                        event(team, LEADER, "report_question_defaulted",
                              {"metric_id": mid, "purpose": purpose, "report_version": version,
                               "question": item.question})
                    if final:
                        team["final_findings"][mid] = copy.deepcopy(f)
                    team["finding_history"].append(copy.deepcopy(f))
                    if f["risk"] == "serious_service_risk":
                        team["risk_alerts"].append({"source_agent": LEADER, "metric_id": mid,
                            "severity": f["risk"], "evidence_ids": f["evidence_ids"], "reason": f["reason"]})
                self._consume(data, agent, purpose, raw, "items", requested, accept, version)
            self._check_failed(data)
        if set(team["draft"]) == set(data["team_plan"]["selected_metric_ids"]):
            report = {"version": version, "round": team["round"], "final": final,
                      "items": copy.deepcopy(team["draft"]), "created_at": now()}
            team["reports"].append(report)
            team["draft"] = {}
            event(team, LEADER, "final_adjudication" if final else "report_published",
                  {"version": version, "round": team["round"], "items": report["items"]})
            if final:
                self._finish(data)
            else:
                team["round"] += 1
                team["phase"] = "feedback"

    async def _feedback(self, data):
        team = data["team"]
        report = team["reports"][-1]
        round_key = str(team["round"])
        feedback = team["feedback"].setdefault(round_key, {})
        requests = []
        for agent in PERSPECTIVES:
            self._send_once(data, f"report:{round_key}:{agent}", LEADER, agent, "REPORT_REVIEW",
                            report, round_number=team["round"], version=report["version"])
            self._bus(data).check_inbox(agent)
            current = team["tasks"][agent]
            owned = feedback.setdefault(agent, {})
            todo = [mid for mid in current["metric_ids"] if mid not in owned]
            if not todo:
                self._drain(data, agent, "current_report_feedback_submitted")
                self._send_once(data, f"feedback:{round_key}:{agent}", agent, LEADER, "REPORT_FEEDBACK",
                                owned, round_number=team["round"], version=report["version"])
                continue
            requested = todo[:current.get("batch_size", 2)]
            purpose = "evaluator_feedback_" + round_key
            payload = self._base(data, agent, purpose, requested)
            payload.update(report_version=report["version"], round=team["round"],
                           current_report={mid: report["items"][mid] for mid in requested},
                           own_initial={mid: team["initial_evaluations"][agent][mid] for mid in requested},
                           own_latest={mid: current["findings"][mid] for mid in requested})
            requests.append((agent, purpose, EVALUATOR_FEEDBACK, payload, FeedbackBatch.model_json_schema()))
        for agent, payload, raw in await self._ask(data, requests) if requests else []:
            purpose = "evaluator_feedback_" + round_key
            def accept(mid, value, owner=agent):
                item = Feedback.model_validate(value)
                self.tools.check_evidence(team, item.evidence_ids)
                candidate = report["items"][mid]["finding"]
                if item.decision == "agree" and item.issue_type != "none":
                    raise ValueError("Agreement cannot retain an unresolved issue")
                if item.decision == "agree" and candidate["status"] == "EVALUATED" and not item.evidence_ids:
                    raise ValueError("Agreement with a score needs original supporting evidence")
                if item.revised_finding is not None:
                    proposal = item.revised_finding.model_dump()
                    if proposal["metric_id"] != mid:
                        raise ValueError("Revision cannot change another metric")
                    if item.decision == "agree" and (proposal["status"], proposal["score"]) != (candidate["status"], candidate["score"]):
                        raise ValueError("An incompatible proposed score cannot be agreement")
                    result = self.tools.submit(data, owner, {"findings": [proposal]})
                    if result["rejected"]:
                        raise ValueError(result["rejected"][0]["error"])
                owned_feedback = {**item.model_dump(), "feedback_id": uid("feedback"), "agent_id": owner,
                                  "report_version": report["version"], "round": team["round"]}
                feedback[owner][mid] = owned_feedback
            self._consume(data, agent, purpose, raw, "feedback", payload["requested_metric_ids"],
                          accept, report["version"])
        self._check_failed(data)
        selected = set(data["team_plan"]["selected_metric_ids"])
        if all(set(feedback.get(agent, {})) == selected for agent in PERSPECTIVES):
            # Publish the last response messages before Leader reads its inbox.
            for agent in PERSPECTIVES:
                self._drain(data, agent, "current_report_feedback_submitted")
                self._send_once(data, f"feedback:{round_key}:{agent}", agent, LEADER, "REPORT_FEEDBACK",
                                feedback[agent], round_number=team["round"], version=report["version"])
            self._drain(data, LEADER, "all_current_version_feedback_received")
            team["score_gaps"] = self._gaps(data)
            team["phase"] = "revision"

    def _finish(self, data):
        team = data["team"]
        for current in team["tasks"].values():
            current["status"] = "COMPLETED"
        team.update(phase="done", stop_reason="completed")
        event(team, LEADER, "discussion_closed", {"rounds": team["round"],
              "methods": {mid: f.get("decision_method") for mid, f in team["final_findings"].items()}})
