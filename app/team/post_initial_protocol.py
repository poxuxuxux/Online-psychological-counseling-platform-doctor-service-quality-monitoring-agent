# 环节：初评后三阶段赋权；用途：先完整独立初评，再由Leader不受同伴适用性意见限制地选项赋权。
import copy

from app.domain.models import now
from app.team.lead_protocol import LEADER, PERSPECTIVES, LeaderProtocol, initialize_protocol
from app.team.prompts_post_initial import INITIAL_ALL, STAGE_PROMPTS
from app.team.protocol_models import Plan
from app.team.state import event
from app.team.tools import TeamTools
from app.team.weights import average_stage_weights, normalize_weights

PROTOCOL_V2 = "leader-review-v2"
WEIGHT_POLICY = "three-stage-normalize-mean-v1"


def initialize_post_initial(skills, run_id):
    team = initialize_protocol(skills, run_id)
    team.update(protocol=PROTOCOL_V2, phase="initial", weighting_stages={})
    team["prompt_version"] = "post-initial-prompts-2.0.5"
    mids = list(skills["metrics"])
    for current in team["tasks"].values():
        current.update(metric_ids=mids, skills_read=True)
    return team


class PostInitialProtocol(LeaderProtocol):
    def _base(self, data, agent, purpose, requested):
        payload = super()._base(data, agent, purpose, requested)
        payload["protocol"] = PROTOCOL_V2
        if purpose == "initial_evaluation":
            payload.pop("weights", None)
            payload["initial_scope"] = "all_catalog_metrics"
        return payload

    def _prepare_initial(self, data):
        team = data["team"]
        if "all_metrics_assigned" in team:
            return
        data["team_plan"] = {"planning_complete": False, "selected_metric_ids": [],
                             "weights": {}, "initial_metric_ids": list(data["skills"]["metrics"])}
        for current in team["tasks"].values():
            current["time_facts"] = TeamTools.time_facts(data["session"])
        for message in data["session"]["messages"]:
            if (message["message_kind"] == "dialogue" and message["modality"] == "text"
                    and message["role"] in {"doctor", "patient"} and message["content"].strip()):
                eid = "e-" + message["message_id"]
                team["evidence"][eid] = {"evidence_id": eid, "session_id": data["session"]["session_id"],
                    "message_id": message["message_id"], "turn_id": message["sequence"],
                    "speaker": message["role"], "original_text": message["content"],
                    "source_agent": "context_manager", "related_indicators": [], "created_at": now()}
        for agent in PERSPECTIVES:
            self._send_once(data, "task:" + agent, LEADER, agent, "TASK_ASSIGNMENT",
                            {"metric_ids": list(data["skills"]["metrics"]),
                             "scope": "all_metrics_initial_only", "weighting": "not_yet_performed"})
        team["all_metrics_assigned"] = True

    async def _initial(self, data):
        self._prepare_initial(data)
        await super()._initial(data)
        if data["team"]["phase"] == "report":
            data["team"]["phase"] = "scenario"

    async def _ask(self, data, requests):
        # Keep the historical protocol's prompts immutable; only replace the v2 initial prompt.
        suffix = ("\n本协议的保留集合在全量初评之后由Leader确定，不受评价者适用性意见限制。"
                  "若当前保留项在初评中被标为不适用，必须按Leader问题重新核对触发事实，"
                  "可以有据修订也可以有据反对，不能仅沿用旧标记。权重为三阶段平均，无等权起点或±20%限幅。")
        requests = [(agent, purpose, INITIAL_ALL if purpose == "initial_evaluation"
                     else system.replace("和同一±20%约束", "") + suffix, payload, schema)
                    for agent, purpose, system, payload, schema in requests]
        return await super()._ask(data, requests)

    def _gaps(self, data):
        plan = data.get("team_plan", {})
        if not plan.get("planning_complete"):
            return super()._gaps({**data, "team_plan": {**plan, "selected_metric_ids": list(data["skills"]["metrics"])}})
        return super()._gaps(data)

    async def _scenario(self, data):
        await self._stage(data, "scenario", "distribution")

    async def _distribution(self, data):
        await self._stage(data, "distribution", "relevance")

    async def _relevance(self, data):
        await self._stage(data, "relevance", "selection")

    async def _stage(self, data, stage, next_phase):
        mids = list(data["skills"]["metrics"])
        purpose = "leader_weight_" + stage
        payload = self._base(data, LEADER, purpose, mids)
        payload.pop("weights", None)
        payload.pop("finding_schema", None)
        payload["previous_weighting_stages"] = copy.deepcopy(data["team"]["weighting_stages"])
        if stage == "distribution":
            payload["initial_evaluations"] = data["team"]["initial_evaluations"]
            payload["score_gaps"] = data["team"]["initial_score_gaps"]
        # Scenario is committed before any score is exposed; relevance emphasizes patient needs.
        if stage == "relevance":
            payload["patient_statements"] = [m for m in payload["dialogue"]["messages"] if m["role"] == "patient"]
        results = await self._ask(data, [(LEADER, purpose, STAGE_PROMPTS[stage], payload, Plan.model_json_schema())])
        for agent, _, raw in results:
            if raw is None:
                continue
            try:
                proposal = Plan.model_validate(raw)
                ids = [item.metric_id for item in proposal.selected + proposal.excluded]
                if len(ids) != len(set(ids)) or set(ids) != set(mids):
                    raise ValueError("Every catalog metric must occur exactly once in this Leader stage")
                candidates = {item.metric_id: item.candidate_weight for item in proposal.selected}
                vector = normalize_weights(candidates)
                stored = {**proposal.model_dump(), "stage": stage, "weights": vector,
                          "candidate_weights": candidates}
                data["team"]["weighting_stages"][stage] = stored
                event(data["team"], LEADER, "weighting_stage_completed", copy.deepcopy(stored))
                data["team"]["phase"] = next_phase
            except (ValueError, TypeError, KeyError) as error:
                self._error(data, agent, purpose, stage, error)
        self._check_failed(data)

    async def _selection(self, data):
        team = data["team"]
        stages = [team["weighting_stages"][stage] for stage in ("scenario", "distribution", "relevance")]
        try:
            weights = average_stage_weights([stage["weights"] for stage in stages])
        except ValueError:
            # Do not silently divide by two or invent equal weights for a failed analysis.
            from app.team.lead_protocol import ProtocolStop
            raise ProtocolStop("weight_stage_incomplete") from None
        all_mids = list(data["skills"]["metrics"])
        reasons = {mid: "; ".join(item["reason"] for stage in stages for item in stage["selected"]
                                  if item["metric_id"] == mid) for mid in weights}
        data["team_plan"] = {
            "planning_complete": True, "policy": PROTOCOL_V2, "weight_policy": WEIGHT_POLICY,
            "selected_metric_ids": list(weights), "initial_metric_ids": all_mids,
            "weights": weights, "candidate_weights": weights, "weight_deviation": None,
            "context_summary": stages[0]["context_summary"],
            "selected": [{"metric_id": mid, "reason": reasons[mid], "candidate_weight": w}
                         for mid, w in weights.items()],
            "excluded": [{"metric_id": mid, "reason": "; ".join(item["reason"] for stage in stages
                          for item in stage["excluded"] if item["metric_id"] == mid)}
                         for mid in all_mids if mid not in weights],
            "weighting_stages": copy.deepcopy(stages),
        }
        for current in team["tasks"].values():
            # Preserve all original findings; only subsequent feedback is scoped to Leader's choice.
            current["metric_ids"] = list(weights)
        for agent in PERSPECTIVES:
            self._send_once(data, "selection:" + agent, LEADER, agent, "SELECTION_AND_WEIGHTS",
                            data["team_plan"])
        event(team, LEADER, "plan_frozen_after_initial", copy.deepcopy(data["team_plan"]))
        team["score_gaps"] = self._gaps(data)
        team["phase"] = "report"
