"""功能：分歧仲裁 Agent 协议与占位实现；核查候选矛盾、复核情境并提出定向重评建议。"""

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import AgentResult, ArbitrationDecision, ConflictCase, ConversationSession


@dataclass(frozen=True)
class ArbitrationContext:
    """仲裁输入：本次会话（供情境复核）、各 Agent 结果与待裁决冲突。"""

    session: ConversationSession
    agent_results: list[AgentResult]
    conflicts: list[ConflictCase]


class ArbitrationAgent(Protocol):
    """仲裁 Agent 核查同一事件/证据上的候选矛盾，裁决结论或转人工。

    不同维度表现不同本身不构成矛盾；Agent 不重写分数、不补造证据、不直接执行重评。

    追回重评以 `ArbitrationDecision.re_evaluation_metric_ids` 建议形式输出，
    由编排器决定是否执行并受"最多一次"限制。
    """

    @property
    def agent_id(self) -> str: ...

    async def arbitrate(self, context: ArbitrationContext) -> list[ArbitrationDecision]: ...


class UnconfiguredArbitrationAgent:
    """占位仲裁 Agent；接入提示词与模型前显式失败，冲突保持未决转人工。"""

    agent_id = "arbitration"

    async def arbitrate(self, context: ArbitrationContext) -> list[ArbitrationDecision]:
        raise NotImplementedError(
            "Arbitration agent is not configured; conflicts stay unresolved for manual review"
        )
