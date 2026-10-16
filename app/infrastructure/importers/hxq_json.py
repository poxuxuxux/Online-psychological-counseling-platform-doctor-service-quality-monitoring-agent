"""Stream the exported data array, normalize provenance without guessing identities."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import ijson

from app.domain.source_data import SourceMessage

EVENTS = {
    "purchase": "已购买图文问诊服务",
    "accepted": "医生已接诊",
    "waiting": "等待医生接诊",
    "withdrawn": "医生已退诊",
}


def stable_ref(*parts: str) -> str:
    # Length framing prevents separator collisions; this is a reference, not anonymization.
    value = "".join(f"{len(str(p))}:{p}" for p in parts)
    return hashlib.sha256(value.encode()).hexdigest()


def iter_threads(path: Path):
    """Memory is bounded by one source thread, not the complete ~1 GB export."""
    with path.open("rb") as stream:

        def checked_events():
            found = False
            for prefix, event, value in ijson.parse(stream):
                if prefix == "data" and event == "start_array":
                    found = True
                yield prefix, event, value
            if not found:
                raise ValueError("Expected a top-level data array")

        for thread in ijson.items(checked_events(), "data.item"):
            if not isinstance(thread, dict) or not isinstance(thread.get("messages"), list):
                raise TypeError("Invalid thread record")
            yield thread


def normalize_time(raw: dict, source_timezone: str) -> tuple[datetime | None, list[str]]:
    issues = []
    numeric, textual = None, None
    value = raw.get("msg_timestamp")
    if value not in (None, ""):
        try:
            number = float(value)
            numeric = datetime.fromtimestamp(number / 1000 if abs(number) >= 1e11 else number, UTC)
        except (ValueError, TypeError, OverflowError, OSError):
            issues.append("invalid_numeric_timestamp")
    if raw.get("create_time"):
        try:
            textual = datetime.fromisoformat(str(raw["create_time"]))
            if textual.tzinfo is None:
                textual = textual.replace(tzinfo=ZoneInfo(source_timezone))
            textual = textual.astimezone(UTC)
        except (ValueError, TypeError):
            issues.append("invalid_create_time")
    if numeric and textual and abs((numeric - textual).total_seconds()) > 1:
        return None, issues + ["timestamp_conflict"]
    timestamp = numeric or textual
    if timestamp is None:
        issues.append("missing_timestamp")
    return timestamp, issues


def normalize_thread(thread: dict, source_id: str, source_timezone: str = "Asia/Shanghai"):
    thread_id = thread.get("chat_session_id")
    if thread_id in (None, ""):
        raise ValueError("Missing thread ID")
    seen = set()
    messages = []
    for sequence, raw in enumerate(thread["messages"]):
        if not isinstance(raw, dict):
            raise TypeError("Invalid message record")
        original_id = raw.get("message_id")
        if original_id in (None, ""):
            raise ValueError("Missing message ID")
        ref = stable_ref(source_id, str(thread_id), str(original_id))
        if ref in seen:
            raise ValueError("Duplicate message ID within thread")
        seen.add(ref)
        content = raw.get("content")
        if isinstance(content, dict):
            text = next(
                (
                    content[k]
                    for k in ("content", "message", "textContent")
                    if isinstance(content.get(k), str) and content[k].strip()
                ),
                "",
            )
        else:
            text = content if isinstance(content, str) else ""
        timestamp, issues = normalize_time(raw, source_timezone)
        kind = str(raw.get("message_kind", "unknown"))
        if raw.get("is_system_notification") is True:
            if kind != "system_notification":
                issues.append("message_kind_conflict")
            kind = "system_notification"
        object_name = str(raw.get("object_name", "unknown"))
        if kind == "dialogue" and object_name != "RC:TxtMsg":
            issues.append("unparsed_content")
        event = next((event for event, phrase in EVENTS.items() if phrase in text), None)
        if kind != "system_notification":
            event = None
        order = raw.get("order_no")
        messages.append(
            SourceMessage(
                message_id=ref,
                sequence=sequence,
                role=str(raw.get("role", "unknown")),
                kind=kind,
                object_name=object_name,
                text=text,
                timestamp=timestamp,
                order_ref=str(order).strip() if order is not None and str(order).strip() else None,
                event=event,
                issues=tuple(issues),
            )
        )
    return messages
