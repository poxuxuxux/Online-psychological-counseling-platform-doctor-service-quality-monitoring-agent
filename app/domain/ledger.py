"""功能：定义共享通信池的运行账本契约；阶段事件、任务单与结论消息，均为带来源与版本的结构化记录。"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

EvaluationEventType = Literal[
    "task.published",
    "agent.started",
    "agent.completed",
    "agent.failed",
    "verification.completed",
    "arbitration.completed",
    "re_evaluation.requested",
    "summary.completed",
    "review.gated",
]


class EvaluationEvent(BaseModel):
    """阶段事件；append-only，按 run_id 隔离，payload 只携带对象 ID 不携带正文。"""

    event_id: str
    run_id: str
    event_type: EvaluationEventType
    source: str
    component_version: str | None = None
    occurred_at: datetime | None = None
    payload_refs: dict[str, str] = Field(default_factory=dict)


class TaskAssignment(BaseModel):
    """任务单；由协调器发布，Agent 只读取被授权给自己的任务单。"""

    task_id: str
    run_id: str
    agent_id: str
    evaluation_id: str
    session_id: str
    skill_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    context_ref: str
    status: Literal["published", "accepted", "completed", "failed"] = "published"


class AgentMessage(BaseModel):
    """Agent 发布到池的结构化结论消息；正文留在结果存储，池内只存引用与摘要。"""

    message_id: str
    run_id: str
    agent_id: str
    kind: Literal[
        "finding",
        "verification",
        "revision_request",
        "revision_response",
        "arbitration",
        "summary",
    ]
    result_ref: str
    digest: str = ""
    component_version: str | None = None
    correlation_id: str | None = None
    supersedes_message_id: str | None = None


class SharedLedger(Protocol):
    """共享通信池仓储协议；实现必须 append-only、按 run_id 隔离并保留写入顺序。"""

    async def append_event(self, event: EvaluationEvent) -> None: ...

    async def append_task(self, task: TaskAssignment) -> None: ...

    async def update_task_status(
        self,
        run_id: str,
        task_id: str,
        status: Literal["accepted", "completed", "failed"],
    ) -> None: ...

    async def append_message(self, message: AgentMessage) -> None: ...

    async def events(self, run_id: str) -> list[EvaluationEvent]: ...

    async def tasks(self, run_id: str) -> list[TaskAssignment]: ...

    async def messages(self, run_id: str) -> list[AgentMessage]: ...
