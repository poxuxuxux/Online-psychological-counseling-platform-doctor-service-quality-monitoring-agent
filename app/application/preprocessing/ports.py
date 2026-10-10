"""功能：定义预处理依赖的外部能力端口；具体适配器由 infrastructure 实现。"""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.models import MediaAsset, TranscriptInfo

MaskCategory = Literal["phone", "identity", "name", "location", "account", "other"]


class RedactionRecord(BaseModel):
    """一条脱敏映射；原文片段只允许保存在隔离映射库中，供审计与复核。"""

    message_id: str
    rule_id: str
    masked_span: str
    replacement: str
    category: MaskCategory = "other"


class RedactionResult(BaseModel):
    """单条消息的脱敏输出；records 需立即写入隔离映射库。"""

    redacted_text: str
    records: list[RedactionRecord] = Field(default_factory=list)


class Transcriber(Protocol):
    """音视频转写端口；实现必须记录引擎名与版本，且不得修改转写语义。"""

    @property
    def engine_name(self) -> str: ...

    @property
    def engine_version(self) -> str: ...

    async def transcribe(self, media: MediaAsset) -> TranscriptInfo: ...


class ContentRedactor(Protocol):
    """文本脱敏端口；ruleset_version 用于报告追溯，规则未审定前不得启用。"""

    @property
    def ruleset_version(self) -> str: ...

    def redact(self, message_id: str, text: str) -> RedactionResult: ...


class RedactionMapRepository(Protocol):
    """脱敏映射的隔离仓储；访问需要审计，映射永远不进入 Agent 输入。"""

    async def save(self, session_id: str, records: list[RedactionRecord]) -> None: ...

    async def get(self, session_id: str) -> list[RedactionRecord]: ...


class MediaStorage(Protocol):
    """原始媒体受控存储端口；生产实现需加密、访问控制和保留策略。"""

    async def save(
        self,
        media_id: str,
        data: bytes,
        modality: Literal["audio", "video"],
        mime_type: str | None = None,
    ) -> str:
        """保存原始媒体并返回受控存储引用。"""
        ...

    async def read(self, storage_ref: str) -> bytes:
        """按引用读取原始媒体；引用必须来自本存储生成的白名单。"""
        ...
