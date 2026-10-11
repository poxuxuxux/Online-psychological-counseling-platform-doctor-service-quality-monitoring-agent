"""功能：管理与情境识别 Agent 协议与占位实现；只产出候选路由与情境说明，指派权在确定性校验。"""

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.models import ConversationSession, HistoryContext, RiskTrigger


@dataclass(frozen=True)
class ManagerContext:
    """管理输入：本次会话、历史上下文可用性与风险候选，均为已授权的受控信息。"""

    session: ConversationSession
    history_context: HistoryContext | None = None
    risk_candidates: list[RiskTrigger] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateRoutePlan:
    """管理 Agent 的产出：候选计划；必须经确定性校验确认后才生效。

    LLM 不直接决定哪些 Agent 被运行——最终指派由确定性策略路由器与
    Agent 白名单校验把关。
    """

    candidate_agent_ids: tuple[str, ...] = ()
    applicable_metric_ids: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    needs_history_context: bool = False


class ManagerAgent(Protocol):
    """管理与情境识别 Agent：识别事件、拆解任务、判断适用指标与历史背景需求。"""

    @property
    def agent_id(self) -> str: ...

    async def plan(self, context: ManagerContext) -> CandidateRoutePlan: ...


class UnconfiguredManagerAgent:
    """占位管理 Agent；未接入提示词与模型前显式失败，流程回退确定性默认路由。"""

    agent_id = "manager"

    async def plan(self, context: ManagerContext) -> CandidateRoutePlan:
        raise NotImplementedError(
            "Manager agent is not configured; deterministic default routing is used"
        )
