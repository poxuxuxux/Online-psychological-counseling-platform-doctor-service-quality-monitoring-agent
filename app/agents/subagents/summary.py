"""功能：总结 Agent 协议与占位实现；汇总评价结果，生成 6 维画像叙述、总评分说明与改进意见。"""

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import (
    AgentResult,
    ConversationSession,
    ImprovementSuggestion,
    QualityProfile,
)


@dataclass(frozen=True)
class SummaryContext:
    """总结输入：确定性画像、Agent 结果及评分后复核门控的结论和原因。

    画像与总评分由确定性评分汇总器计算后传入；本 Agent 只做叙述与改进建议。
    """

    session: ConversationSession
    quality_profile: QualityProfile
    agent_results: list[AgentResult]
    review_required: bool
    review_reasons: list[str]


class SummaryAgent(Protocol):
    """总结 Agent 消费确定性画像生成叙述与改进意见；不得重算或改写任何分数。

    改进意见基于评分锚点与覆盖缺口，不构成临床督导或诊疗建议。
    """

    @property
    def agent_id(self) -> str: ...

    async def summarize(self, context: SummaryContext) -> list[ImprovementSuggestion]: ...


class UnconfiguredSummaryAgent:
    """占位总结 Agent；接入提示词与模型前显式失败，报告保留原始结果。"""

    agent_id = "summary"

    async def summarize(self, context: SummaryContext) -> list[ImprovementSuggestion]:
        raise NotImplementedError("Summary agent is not configured; report keeps raw findings")
