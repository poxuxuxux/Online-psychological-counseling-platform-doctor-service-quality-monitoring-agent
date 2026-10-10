"""功能：文本脱敏适配器与脱敏映射的隔离内存仓储。"""

from app.application.preprocessing.ports import (
    RedactionRecord,
    RedactionResult,
)


class SyntheticDemoRedactor:
    """合成演示数据专用脱敏器：不做任何掩码。

    仅允许用于仓库自带的合成会话；接入任何真实或授权数据前，
    必须替换为经过审定的 RuleBasedContentRedactor 规则集。
    """

    ruleset_version = "synthetic-demo"

    def redact(self, message_id: str, text: str) -> RedactionResult:
        """原样返回合成数据；不产生脱敏记录。"""
        return RedactionResult(redacted_text=text, records=[])


class RuleBasedContentRedactor:
    """规则脱敏器骨架；规则集未审定前对任何文本显式失败。"""

    def __init__(self, ruleset_version: str = "unconfigured") -> None:
        self._ruleset_version = ruleset_version

    @property
    def ruleset_version(self) -> str:
        """返回规则集版本；报告用其追溯本次脱敏依据。"""
        return self._ruleset_version

    def redact(self, message_id: str, text: str) -> RedactionResult:
        """拒绝处理；防止未审定的规则漏掉身份信息后流入模型上下文。"""
        raise NotImplementedError(
            "Redaction ruleset is not reviewed; configure an approved ruleset "
            "before processing authorized conversation text"
        )


class InMemoryRedactionMapRepository:
    """进程内脱敏映射仓储；仅供演示，生产实现需访问控制与持久化审计。"""

    def __init__(self) -> None:
        self._records: dict[str, list[RedactionRecord]] = {}

    async def save(self, session_id: str, records: list[RedactionRecord]) -> None:
        """暂存映射；映射本体不进入会话对象或 Agent 输入。"""
        self._records[session_id] = records

    async def get(self, session_id: str) -> list[RedactionRecord]:
        """读取映射，仅供审计与人工复核流程调用。"""
        return list(self._records.get(session_id, []))
