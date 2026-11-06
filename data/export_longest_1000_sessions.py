# 环节：数据处理层；用途：处理本地样本输入或导出，须遵守数据访问边界。
"""Export sessions/messages from longest_1000_sessions.json to CSV without loading it all into memory.

Usage:
    python export_longest_1000_sessions.py                     # export per-message CSV
    python export_longest_1000_sessions.py --mode sessions     # one row per session
    python export_longest_1000_sessions.py --mode both         # export both CSVs
    python export_longest_1000_sessions.py -o out.csv --limit 50
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from read_longest_1000_sessions import DEFAULT_PATH, iter_sessions

MESSAGE_FIELDS = [
    "chat_session_id",
    "message_index",
    "create_time",
    "role",
    "message_kind",
    "content",
]

SESSION_FIELDS = [
    "chat_session_id",
    "dialogue_count",
    "message_count",
    "first_timestamp",
    "last_timestamp",
]


def extract_text(message):
    """Return a plain-text version of a message's content."""
    content = message.get("content")
    if isinstance(content, dict):
        text = content.get("content") or content.get("message")
        content = text if isinstance(text, str) else json.dumps(content, ensure_ascii=False)
    elif not isinstance(content, str):
        content = "" if content is None else json.dumps(content, ensure_ascii=False)
    return content


def extract_timestamp(message):
    return message.get("create_time") or message.get("msg_timestamp") or ""


def export(messages_path=None, sessions_path=None, limit=0, session_id=None):
    message_writer = session_writer = None
    message_file = session_file = None
    n_sessions = n_messages = 0

    try:
        if messages_path is not None:
            message_file = messages_path.open("w", encoding="utf-8-sig", newline="")
            message_writer = csv.DictWriter(message_file, fieldnames=MESSAGE_FIELDS)
            message_writer.writeheader()
        if sessions_path is not None:
            session_file = sessions_path.open("w", encoding="utf-8-sig", newline="")
            session_writer = csv.DictWriter(session_file, fieldnames=SESSION_FIELDS)
            session_writer.writeheader()

        for session in iter_sessions(DEFAULT_PATH):
            sid = session["chat_session_id"]
            if session_id is not None and str(sid) != session_id:
                continue

            messages = session.get("messages", [])
            first_ts = extract_timestamp(messages[0]) if messages else ""
            last_ts = extract_timestamp(messages[-1]) if messages else ""

            if session_writer is not None:
                session_writer.writerow(
                    {
                        "chat_session_id": sid,
                        "dialogue_count": session.get("message_counts", {}).get("dialogue", ""),
                        "message_count": len(messages),
                        "first_timestamp": first_ts,
                        "last_timestamp": last_ts,
                    }
                )

            if message_writer is not None:
                for index, message in enumerate(messages, 1):
                    message_writer.writerow(
                        {
                            "chat_session_id": sid,
                            "message_index": index,
                            "create_time": extract_timestamp(message),
                            "role": message.get("role", "unknown"),
                            "message_kind": message.get("message_kind", "unknown"),
                            "content": extract_text(message),
                        }
                    )
                    n_messages += 1

            n_sessions += 1
            if limit and n_sessions >= limit:
                break
    finally:
        if message_file:
            message_file.close()
        if session_file:
            session_file.close()

    return n_sessions, n_messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["messages", "sessions", "both"], default="messages")
    parser.add_argument("-o", "--output", type=Path, help="Output CSV path (overrides default)")
    parser.add_argument("--limit", type=int, default=0, help="Number of sessions to export (0 for all)")
    parser.add_argument("--session-id", help="Export only this chat_session_id")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be 0 or greater")

    base = DEFAULT_PATH.with_name("longest_1000_sessions")
    if args.output:
        if args.mode == "both" and args.output.suffix == ".csv":
            stem = args.output.with_suffix("")
            messages_path = stem.with_name(stem.name + "_messages.csv")
            sessions_path = stem.with_name(stem.name + "_sessions.csv")
        else:
            messages_path = args.output
            sessions_path = args.output
    elif args.mode == "sessions":
        messages_path = None
        sessions_path = base.with_name(base.name + "_sessions.csv")
    elif args.mode == "both":
        messages_path = base.with_name(base.name + "_messages.csv")
        sessions_path = base.with_name(base.name + "_sessions.csv")
    else:
        messages_path = base.with_name(base.name + "_messages.csv")
        sessions_path = None

    n_sessions, n_messages = export(messages_path, sessions_path, args.limit, args.session_id)

    if sessions_path:
        print(f"Sessions CSV : {sessions_path} ({n_sessions} rows)")
    if messages_path:
        print(f"Messages CSV : {messages_path} ({n_messages} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
