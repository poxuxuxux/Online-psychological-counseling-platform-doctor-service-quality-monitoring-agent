"""功能：定义应用层依赖的仓储端口；具体实现由 infrastructure 提供并经组合根注入。"""

from typing import Protocol

from app.domain.models import ConversationSession


class SessionRepository(Protocol):
    """会话仓储端口；生产实现应增加访问控制、迁移和审计。"""

    async def get(self, session_id: str) -> ConversationSession | None:
        """按会话 ID 获取已规范化会话。"""
        ...

    async def save(self, session: ConversationSession) -> None:
        """保存会话；不得记录或提交不必要的原始患者标识。"""
        ...
