# 环节：开发运维辅助层；用途：协助本地服务启动或受控样本准备。
"""Stream private source threads into complete order-scoped, size-bounded test inputs.

This removes source IDs/metadata and common contact identifiers. Free text can still
contain identifying information: output remains private, never synthetic/public demo.
No message truncation, generated dialogue or inferred consultation closure.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import ijson

from app.domain.models import Session


def text_content(message):
    content = message.get("content")
    if isinstance(content, dict):
        content = content.get("content") or content.get("message")
    return content if isinstance(content, str) else ""


def redact(text):
    for pattern in (
        r"(?<!\d)1[3-9]\d{9}(?!\d)",
        r"(?<!\d)\d{17}[\dXx](?!\d)",
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"https?://\S+",
    ):
        text = re.sub(pattern, "[联系方式已隐藏]", text)
    return text


def prepare(source, output, count=3):
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    scanned = 0
    with source.open("rb") as stream:
        for thread in ijson.items(stream, "data.item"):
            scanned += 1
            orders = defaultdict(list)
            for message in thread.get("messages", []):
                if message.get("order_no"):
                    orders[str(message["order_no"])].append(message)
            for order, raw in orders.items():
                dialogue = [m for m in raw if m.get("message_kind") == "dialogue"]
                if not 12 <= len(dialogue) <= 60:
                    continue
                if any(
                    m.get("object_name") != "RC:TxtMsg" or not text_content(m) for m in dialogue
                ):
                    continue
                if {m.get("role") for m in dialogue} != {"doctor", "patient"}:
                    continue
                if not 1500 <= sum(len(text_content(m)) for m in raw) <= 9000 or len(raw) > 100:
                    continue
                if any(not m.get("msg_timestamp") for m in raw):
                    continue
                raw = sorted(raw, key=lambda m: int(m["msg_timestamp"]))
                # A source thread spans years; even order grouping must not merge long follow-ups.
                if int(raw[-1]["msg_timestamp"]) - int(raw[0]["msg_timestamp"]) > 7 * 86400000:
                    continue
                messages = []
                names = set()
                for m in raw:
                    match = re.match(r"^([\u4e00-\u9fff]{2,4})[（(](?:男|女)", text_content(m))
                    if match:
                        names.add(match[1])
                for i, m in enumerate(raw):
                    content = text_content(m)
                    cleaned = redact(content)
                    for name in names:
                        cleaned = cleaned.replace(name, "[姓名已隐藏]")
                    is_dialogue = m.get("message_kind") == "dialogue"
                    messages.append(
                        {
                            "message_id": f"m{i}",
                            "sequence": i,
                            "role": m["role"] if is_dialogue else "system",
                            "message_kind": "dialogue" if is_dialogue else "system_notification",
                            "content": cleaned if content else "[非文本平台事件]",
                            "timestamp": datetime.fromtimestamp(
                                int(m["msg_timestamp"]) / 1000, UTC
                            ).isoformat(),
                            "redaction_applied": content != cleaned,
                        }
                    )
                # Explicit platform end event is required before allowing absence claims.
                closed = any(
                    m["role"] == "system"
                    and re.search(
                        "咨询已结束|服务已结束|订单已结束|问诊已结束|问诊服务已结束", m["content"]
                    )
                    for m in messages
                )
                start_event = next(
                    (
                        m
                        for m in messages
                        if m["role"] == "system"
                        and re.search("已接诊|咨询开始|服务开始", m["content"])
                    ),
                    None,
                )
                context = {
                    "boundary_basis": "source_order_id",
                    "order_messages_complete": True,
                    "closure_confirmed": closed,
                    "privacy": "private_text_not_fully_anonymized",
                }
                if start_event:
                    context.update(
                        consultation_started_at=start_event["timestamp"],
                        start_basis="order_timestamp",
                        start_message_id=start_event["message_id"],
                    )
                identity = hashlib.sha256(
                    (str(thread["chat_session_id"]) + order).encode()
                ).hexdigest()[:16]
                session = Session.model_validate(
                    {
                        "session_id": "real-order-" + identity,
                        "source_id": "private-real-sample",
                        "history_complete": False,
                        "observation_complete": closed,
                        "session_time": messages[0]["timestamp"],
                        "service_context": context,
                        "messages": messages,
                    }
                )
                path = output / (session.session_id + ".json")
                path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
                manifest.append(
                    {
                        "file": path.name,
                        "messages": len(messages),
                        "dialogue_messages": len(dialogue),
                        "closure_confirmed": closed,
                        "start_confirmed": bool(start_event),
                        "characters": sum(len(m["content"]) for m in messages),
                    }
                )
                break  # Different source threads, not multiple orders of the same person.
            if len(manifest) >= count:
                break
    result = {
        "scanned_threads": scanned,
        "samples": manifest,
        "privacy": "Private samples; free text requires review before any public use.",
    }
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/longest_1000_sessions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/private/quality-samples"))
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.count <= 20:
        parser.error("count must be between 1 and 20")
    print(json.dumps(prepare(args.source, args.output, args.count), ensure_ascii=False, indent=2))
