"""功能：对跨 Agent 冲突给出可审阅的仲裁状态，不用平均分掩盖分歧。"""

from dataclasses import dataclass

from app.domain.models import AgentResult


@dataclass(frozen=True)
class ArbitrationOutcome:
    """仲裁输出；证据或规则不足时明确保持 unresolved。"""

    status: str
    explanation: str
    accepted_agent_ids: tuple[str, ...] = ()


class DisagreementArbitrator:
    """提供仲裁策略扩展点；正式规则需依指标锚点和证据质量制定。"""

    def arbitrate(self, results: list[AgentResult]) -> ArbitrationOutcome:
        """占位策略不编造裁决；有多个结果时交由人工/后续规则审查。"""
        if len(results) < 2:
            return ArbitrationOutcome("not_needed", "No cross-agent disagreement to assess")
        return ArbitrationOutcome(
            "unresolved",
            "Arbitration rules are not configured; preserve original agent findings.",
        )
