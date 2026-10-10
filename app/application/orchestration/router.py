"""功能：根据显式规则决定参与评价的 Agent 和候选 Skill，不负责授权放行。"""

from dataclasses import dataclass

from app.domain.models import ConversationSession


@dataclass(frozen=True)
class RoutePlan:
    """路由结果；便于记录、复核和测试本次任务为何选择这些模块。"""

    agent_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    reasons: tuple[str, ...] = ()


class PolicyRouter:
    """初始确定性路由器；此处不调用模型，也不动态导入未注册代码。"""

    def route(self, session: ConversationSession) -> RoutePlan:
        """返回 MVP 的默认评估组合；更精细的情境规则由团队后续补充。"""
        if not session.messages:
            return RoutePlan(agent_ids=(), skill_ids=(), reasons=("empty_session",))
        return RoutePlan(
            agent_ids=("professional_service", "process_response", "empathy_relationship"),
            skill_ids=(),
            reasons=("default_mvp_route",),
        )
