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
INITIAL_GROUPS = {
    "evaluator:effectiveness": ({"D1", "D3"}, "专业信息咨询 Agent"),
    "evaluator:empathy": ({"D4", "D6"}, "情感-评价支持 Agent"),
    "evaluator:collaboration": ({"D2", "D5"}, "行动与资源支持 Agent"),
}


def initialize_post_initial(skills, run_id):
    team = initialize_protocol(skills, run_id)
    team.update(protocol=PROTOCOL_V2, phase="initial", weighting_stages={})
    team["prompt_version"] = "post-initial-prompts-2.1.0"
    team["grouped_initial"] = True
    mids = list(skills["metrics"])
    for current in team["tasks"].values():
        current.update(metric_ids=mids, skills_read=True)
    for agent, (dimensions, name) in INITIAL_GROUPS.items():
        team["tasks"][agent].update(
            metric_ids=[mid for mid in mids if skills["metrics"][mid]["dimension_id"] in dimensions],
            perspective=name,
        )
    return team


class PostInitialProtocol(LeaderProtocol):
    def _base(self, data, agent, purpose, requested):
        payload = super()._base(data, agent, purpose, requested)
        payload["protocol"] = PROTOCOL_V2
        if purpose == "initial_evaluation":
            payload.pop("weights", None)
            payload["initial_scope"] = ("assigned_dimensions" if data["team"].get("grouped_initial")
                                        else "all_catalog_metrics")
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
                            {"metric_ids": team["tasks"][agent]["metric_ids"],
                             "scope": "assigned_metrics_initial_only", "weighting": "not_yet_performed"})
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
        if data["team"].get("grouped_initial"):
            requests = [(agent, purpose, self._grouped_prompt(purpose, system), payload, schema)
                        for agent, purpose, system, payload, schema in requests]
        return await super()._ask(data, requests)

    @staticmethod
    def _grouped_prompt(purpose, system):
        if purpose == "initial_evaluation":
            return system.replace(
                "本协议先全指标独立初评，再由Leader选择和赋权。逐项评价完整候选库，当前批次只返回requested_metric_ids。",
                "本协议先按维度分工初评，再由Leader选择和赋权。只评本批requested_metric_ids，不替其他Agent初评。",
            )
        system = system.replace("三份全量初评", "三份分工初评（合计覆盖完整目录，每项一份）")
        system = system.replace(
            "阶段2评分与证据分布：查看三方初评、原文和已确认情境，检查状态、分差、证据与理由。\n"
            "分数接近或证据充分可以支持保留，但不是唯一条件；分差大、低分、难评不等于不重要。",
            "阶段2评分与证据分布：逐项核对负责人初评、原文与已确认情境。每项仅一份初评，"
            "依据证据与任务相关性决定是否保留；低分和难评不等于不重要。",
        ).replace("同分不等于事实正确。", "")
        system = system.replace(
            "不取多数票或平均来代替判断。score_gaps中的原始分差>=3必须在question提出有针对性的问题；\n"
            "分差小也要检查事实、证据、适用性冲突。不要直接要求统一数字或重跑所有项目。",
            "每项仅一份负责人初评。发现证据矛盾、适用性疑点或与负责人结论不一致时，在question明确核对事项。",
        ).replace("三方都须检查综合报告而非只审大分差。", "三方都须检查综合报告。")
        if purpose.startswith("evaluator_feedback_"):
            system += "\nown_initial和own_latest只包含你有记录的项目；没有初评的项目直接核对P0及原文，仍须提交反馈。"
        return system

    def _gaps(self, data):
        if data["team"].get("grouped_initial"):
            return {}
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
            if not data["team"].get("grouped_initial"):
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
