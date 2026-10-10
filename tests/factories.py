"""功能：测试共用的会话与消息构造工具。"""

from datetime import datetime, timedelta

from app.domain.models import ConversationSession, MediaAsset, Message, Modality, SpeakerRole

BASE_TIME = datetime(2026, 10, 10, 9, 0, 0)


def make_message(
    message_id: str,
    role: SpeakerRole = "doctor",
    content: str = "我理解你现在的感受。",
    sequence: int = 0,
    timestamp: datetime | None = None,
    modality: Modality = "text",
    media: MediaAsset | None = None,
    omit_timestamp: bool = False,
) -> Message:
    """构造单条消息；默认按序号生成时间戳，保证 D2 预检不降级。"""
    resolved = timestamp
    if not omit_timestamp and resolved is None:
        resolved = BASE_TIME + timedelta(minutes=sequence)
    return Message(
        message_id=message_id,
        role=role,
        content=content,
        sequence=sequence,
        timestamp=resolved,
        modality=modality,
        media=media,
    )


def make_session(
    session_id: str = "s-001",
    messages: list[Message] | None = None,
) -> ConversationSession:
    """构造会话；默认包含医患各一条带时间戳的消息。"""
    if messages is None:
        messages = [
            make_message("m-001", role="patient", content="我最近总是睡不好。", sequence=0),
            make_message("m-002", role="doctor", content="听起来你已经被失眠困扰了一段时间。", sequence=1),
        ]
    return ConversationSession(session_id=session_id, messages=messages)
