"""功能：约定会话导入器接口，新增文件格式时不修改评价业务流程。"""

from pathlib import Path
from typing import Protocol

from app.domain.models import ConversationSession


class ConversationImporter(Protocol):
    """导入器负责格式解析与字段规范化，不负责推测身份或评价会话。"""

    def import_file(self, path: Path) -> list[ConversationSession]:
        """将一个已授权本地文件转换为规范会话列表。"""
        ...
