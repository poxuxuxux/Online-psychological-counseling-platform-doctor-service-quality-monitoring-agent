"""功能：提供会话仓储的内存实现；端口契约见应用层，组合根负责装配。"""

from app.domain.models import ConversationSession


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
