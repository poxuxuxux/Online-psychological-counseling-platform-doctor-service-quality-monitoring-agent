"""功能：定义人工复核门控接口；硬性风险 > 证据/技术限制 > 常规归档的确定性判断。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ReviewGateDecision:
    """门控输出；原因随报告与案件保留，供操作员理解为何需要复核。"""

    required: bool
    reasons: tuple[str, ...] = ()
    priority: Literal["hard_risk", "evidence_limitation", "routine"] | None = None


class ReviewGate:
    """综合风险/D6 结果、仲裁未决、证据状态、覆盖率和 Agent 失败状态做判断。"""

    def evaluate(
        self,
        agent_results: list,
        quality_profile=None,
        arbitration_summary=None,
        high_risk: bool = False,
    ) -> ReviewGateDecision:
        """占位接口：门控规则接入前显式报错，不默认放行或默认复核。"""
        raise NotImplementedError("Review gate rules are not configured")
