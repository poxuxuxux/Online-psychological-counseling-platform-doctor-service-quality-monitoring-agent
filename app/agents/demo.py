"""功能：提供比赛最小闭环使用的确定性演示 Agent，可被正式模型 Agent 原位替换。"""

from dataclasses import dataclass

from app.domain.models import AgentInput, AgentResult, ConversationEvidenceRef, Finding, Message


@dataclass(frozen=True)
class DemoMetric:
    """一条可复现的演示指标规则。"""

    metric_id: str
    score: float | None
    rationale: str
    keywords: tuple[str, ...] = ()
    applicability: str = "applicable"


class DeterministicDemoAgent:
    """按关键词选择医生原话并生成演示结论；不调用模型，也不用于真实质检。"""

    def __init__(self, agent_id: str, metrics: tuple[DemoMetric, ...]) -> None:
        self.agent_id = agent_id
        self._metrics = metrics

    async def evaluate(self, agent_input: AgentInput) -> AgentResult:
        doctor_messages = [
            message for message in agent_input.session.messages if message.role == "doctor"
        ]
        findings = [self._evaluate_metric(metric, doctor_messages) for metric in self._metrics]
        return AgentResult(agent_id=self.agent_id, status="completed", findings=findings)

    @staticmethod
    def _evaluate_metric(metric: DemoMetric, messages: list[Message]) -> Finding:
        selected = next(
            (
                message
                for message in messages
                if any(keyword in message.content for keyword in metric.keywords)
            ),
            messages[0] if messages else None,
        )
        evidence = []
        if selected is not None and metric.applicability == "applicable":
            evidence = [
                ConversationEvidenceRef(
                    message_ids=[selected.message_id],
                    quote=selected.content,
                    explanation="该结论直接定位到本次咨询中的医生发言。",
                )
            ]
        return Finding(
            metric_id=metric.metric_id,
            metric_version="demo-0.1",
            applicability=metric.applicability,  # type: ignore[arg-type]
            score=metric.score,
            rationale=metric.rationale,
            evidence=evidence,
            confidence_band="medium",
            limitations=["当前为确定性演示规则，正式版本将替换为经验证的指标 Skill 与模型。"],
        )


def build_demo_agents() -> tuple[DeterministicDemoAgent, ...]:
    """构造三个职责隔离的演示 Agent，ID 与正式路由契约保持一致。"""
    return (
        DeterministicDemoAgent(
            "professional_service",
            (
                DemoMetric(
                    "D1",
                    4.2,
                    "医生使用开放式问题继续收集睡眠模式与影响信息，专业信息采集较完整。",
                    ("几点入睡", "会醒几次", "了解一下"),
                ),
                DemoMetric(
                    "D3",
                    4.0,
                    "医生给出了可执行的记录计划，并说明了后续根据记录继续讨论。",
                    ("记录一周", "睡眠情况", "下次"),
                ),
                DemoMetric(
                    "D6.2",
                    None,
                    "本次合成会话未出现需要评价该风险项的行为情境，由指标规则判断为不适用。",
                    applicability="not_applicable",
                ),
            ),
        ),
        DeterministicDemoAgent(
            "process_response",
            (
                DemoMetric(
                    "D2",
                    4.1,
                    "医生回应紧接患者表达，并通过连续追问维持了清晰的咨询节奏。",
                    ("我想先了解", "几点入睡"),
                ),
                DemoMetric(
                    "D5",
                    4.0,
                    "医生说明了下一步安排及需要提前求助的情况，流程交代较明确。",
                    ("及时联系", "下一次", "记录一周"),
                ),
            ),
        ),
        DeterministicDemoAgent(
            "empathy_relationship",
            (
                DemoMetric(
                    "D4",
                    4.5,
                    "医生先承接患者因失眠产生的辛苦感受，再进入信息询问，体现了共情回应。",
                    ("让你很辛苦", "听起来"),
                ),
                DemoMetric(
                    "D6.1",
                    4.2,
                    "医生对症状明显加重的情况给出进一步求助提示，演示规则未发现明显遗漏。",
                    ("明显加重", "及时联系"),
                ),
            ),
        ),
    )
