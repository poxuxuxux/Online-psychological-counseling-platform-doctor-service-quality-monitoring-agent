"""功能：提供会话仓储契约和仅供测试/演示使用的内存实现。"""

from typing import Protocol

from app.domain.models import ConversationSession


class SessionRepository(Protocol):
    """持久化适配器接口；生产实现应增加访问控制、迁移和审计。"""

    async def get(self, session_id: str) -> ConversationSession | None:
        """按会话 ID 获取已规范化会话。"""
        ...

    async def save(self, session: ConversationSession) -> None:
        """保存会话；不得记录或提交不必要的原始患者标识。"""
        ...


class InMemorySessionRepository:
    """进程内临时仓储；应用重启后数据丢失，不适合生产或真实患者数据。"""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    async def get(self, session_id: str) -> ConversationSession | None:
        """从内存字典读取会话，仅供本地演示流程使用。"""
        return self._sessions.get(session_id)

    async def save(self, session: ConversationSession) -> None:
        """暂存会话对象；调用方仍需遵循脱敏和授权要求。"""
        self._sessions[session.session_id] = session
