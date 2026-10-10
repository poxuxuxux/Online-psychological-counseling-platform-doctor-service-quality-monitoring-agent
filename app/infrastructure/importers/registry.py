"""功能：根据导入格式显式查找适配器；新增格式通过注册完成扩展。"""

from app.infrastructure.importers.base import ConversationImporter


class ImporterRegistry:
    """维护格式名到导入器实例的映射，避免业务代码判断文件扩展名。"""

    def __init__(self) -> None:
        self._importers: dict[str, ConversationImporter] = {}

    def register(self, format_name: str, importer: ConversationImporter) -> None:
        """注册文件格式处理器；重复格式作为装配错误处理。"""
        if format_name in self._importers:
            raise ValueError(f"Importer already registered: {format_name}")
        self._importers[format_name] = importer

    def get(self, format_name: str) -> ConversationImporter:
        """返回格式处理器；未知格式不会被静默当成其他格式解析。"""
        try:
            return self._importers[format_name]
        except KeyError as error:
            raise KeyError(f"Importer is not registered: {format_name}") from error
