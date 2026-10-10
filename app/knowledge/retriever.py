"""功能：定义知识检索接口；具体向量库或关键词检索实现可独立替换。"""

from typing import Protocol

from app.domain.models import KnowledgeRef


class KnowledgeRetriever(Protocol):
    """检索器需返回带来源信息的片段，便于在报告中追溯知识依据。"""

    async def search(self, query: str, limit: int = 5) -> list[KnowledgeRef]:
        """按查询检索知识片段；权限过滤和来源校验由具体实现负责。"""
        ...
