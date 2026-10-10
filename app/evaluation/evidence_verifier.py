"""功能：验证 Agent 引用的消息 ID 和原文片段确实存在于本次会话。"""

from app.domain.models import AgentResult, ConversationSession


class EvidenceVerifier:
    """检查可追溯性；更严格的语义支持判断需由后续审核策略补充。"""

    def verify(self, result: AgentResult, session: ConversationSession) -> list[str]:
        """返回问题列表；空列表表示引用定位有效，不代表结论一定正确。"""
        messages = {message.message_id: message.content for message in session.messages}
        issues: list[str] = []
        for finding in result.findings:
            for evidence in finding.evidence:
                cited = [messages.get(message_id) for message_id in evidence.message_ids]
                if not cited or any(content is None for content in cited):
                    issues.append(f"{finding.metric_id}: evidence message ID not found")
                    continue
                if evidence.quote and not any(evidence.quote in content for content in cited):
                    issues.append(f"{finding.metric_id}: quote does not match cited messages")
        return issues
