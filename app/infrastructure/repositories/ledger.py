"""功能：共享通信池的进程内 append-only 账本实现；生产实现需替换为持久化存储并接入审计。"""

from typing import Literal

from app.domain.ledger import AgentMessage, EvaluationEvent, TaskAssignment


class InMemorySharedLedger:
    """进程内账本；记录按 run_id 隔离，写入顺序保留，供审计、进度与复核追溯。"""

    def __init__(self) -> None:
        self._events: dict[str, list[EvaluationEvent]] = {}
        self._tasks: dict[str, list[TaskAssignment]] = {}
        self._messages: dict[str, list[AgentMessage]] = {}

    async def append_event(self, event: EvaluationEvent) -> None:
        """追加阶段事件；不做去重或改写，事件顺序即发生顺序。"""
        self._events.setdefault(event.run_id, []).append(event)

    async def append_task(self, task: TaskAssignment) -> None:
        """发布任务单；同一 run 内 task_id 重复视为装配错误。"""
        tasks = self._tasks.setdefault(task.run_id, [])
        if any(existing.task_id == task.task_id for existing in tasks):
            raise ValueError(f"Task already published: {task.task_id}")
        tasks.append(task)

    async def update_task_status(
        self,
        run_id: str,
        task_id: str,
        status: Literal["accepted", "completed", "failed"],
    ) -> None:
        """更新任务单状态；状态流转历史由事件流单独保留。"""
        for index, task in enumerate(self._tasks.get(run_id, [])):
            if task.task_id == task_id:
                self._tasks[run_id][index] = task.model_copy(update={"status": status})
                return
        raise KeyError(f"Task is not published in run {run_id}: {task_id}")

    async def append_message(self, message: AgentMessage) -> None:
        """追加结论消息；池内只存引用与摘要，不存会话正文。"""
        self._messages.setdefault(message.run_id, []).append(message)

    async def events(self, run_id: str) -> list[EvaluationEvent]:
        """按 run_id 读取事件；返回副本，调用方不能改写账本。"""
        return list(self._events.get(run_id, []))

    async def tasks(self, run_id: str) -> list[TaskAssignment]:
        """按 run_id 读取任务单。"""
        return list(self._tasks.get(run_id, []))

    async def messages(self, run_id: str) -> list[AgentMessage]:
        """按 run_id 读取结论消息。"""
        return list(self._messages.get(run_id, []))
