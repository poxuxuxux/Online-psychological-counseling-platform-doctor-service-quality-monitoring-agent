"""功能：核验 Agent 引用的消息 ID、原文片段和媒体时间区间确实存在且匹配。"""

from app.domain.models import (
    AgentResult,
    ConversationEvidenceRef,
    ConversationSession,
    Message,
)

_FULLWIDTH_TO_HALFWIDTH = {0xFF01 + offset: 0x21 + offset for offset in range(0x5E)}
_FULLWIDTH_TO_HALFWIDTH[0x3000] = 0x20


def _normalize_for_match(text: str) -> str:
    """全角转半角并折叠空白；降低模型引文与原文的表面差异。"""
    return " ".join(text.translate(_FULLWIDTH_TO_HALFWIDTH).split())


def _despace(text: str) -> str:
    """去除全部空白；作为引文匹配的第二道宽容判定，主要服务中文文本。"""
    return text.translate(_FULLWIDTH_TO_HALFWIDTH).replace(" ", "").replace("\t", "").replace("\n", "")


class EvidenceVerifier:
    """确定性核验工具；语义层面的支撑判断由证据核验子 Agent 负责。"""

    def verify(self, result: AgentResult, session: ConversationSession) -> list[str]:
        """返回问题列表；空列表表示引用定位有效，不代表结论一定正确。"""
        messages = {message.message_id: message for message in session.messages}
        issues: list[str] = []
        for finding in result.findings:
            for evidence in finding.evidence:
                cited = [messages.get(message_id) for message_id in evidence.message_ids]
                if not evidence.message_ids or any(message is None for message in cited):
                    issues.append(f"{finding.metric_id}: evidence message ID not found")
                    continue
                if evidence.quote and not self._quote_matches(evidence.quote, cited):
                    issues.append(f"{finding.metric_id}: quote does not match cited messages")
                issues.extend(
                    f"{finding.metric_id}: {issue}"
                    for issue in self._check_media_ranges(cited, evidence)
                )
        return issues

    @staticmethod
    def _quote_matches(quote: str, cited: list[Message | None]) -> bool:
        """先按归一化文本匹配，再按去空白文本匹配；两者都不中才算不匹配。"""
        normalized_quote = _normalize_for_match(quote)
        despaced_quote = _despace(quote)
        for message in cited:
            if message is None:
                continue
            if normalized_quote in _normalize_for_match(message.content):
                return True
            if despaced_quote and despaced_quote in _despace(message.content):
                return True
        return False

    @staticmethod
    def _check_media_ranges(cited: list[Message | None], evidence: ConversationEvidenceRef) -> list[str]:
        """校验媒体时间区间：范围不能超出原始媒体时长，且只能标注在媒体消息上。"""
        issues: list[str] = []
        if not evidence.media_time_ranges:
            return issues
        for message in cited:
            if message is None:
                continue
            if message.media is None:
                issues.append(f"media time range on non-media message {message.message_id}")
                continue
            if message.media.duration_seconds is None:
                issues.append(f"unknown media duration for {message.message_id}")
                continue
            for time_range in evidence.media_time_ranges:
                if time_range.end_seconds > message.media.duration_seconds:
                    issues.append(
                        f"media time range exceeds duration for {message.message_id}"
                    )
        return issues
