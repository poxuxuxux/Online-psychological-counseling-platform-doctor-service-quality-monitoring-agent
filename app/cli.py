"""Local, aggregate-only data preview and an explicit synthetic Qwen connectivity check."""

import argparse
import asyncio
import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.application.preprocessing.rounds import first_response, split_rounds
from app.infrastructure.importers.hxq_json import iter_threads, normalize_thread, stable_ref
from app.infrastructure.llm.qwen import QwenConfig, QwenProvider
from app.infrastructure.repositories.local_jobs import LocalJobStore


def preview(path: Path, limit: int, timezone: str) -> dict:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    counts, issues = Counter(), Counter()
    for thread in iter_threads(path):
        messages = normalize_thread(thread, "hxq-export", timezone)
        rounds = split_rounds(messages, stable_ref("hxq-export", str(thread["chat_session_id"])))
        counts["threads"] += 1
        counts["messages"] += len(messages)
        counts["order_groups"] += sum("missing_order" not in r.issues for r in rounds)
        counts["unassigned_messages"] += sum("missing_order" in r.issues for r in rounds)
        for round_ in rounds:
            issues.update(round_.issues)
            timing = first_response(round_)
            counts["observed_first_response_intervals"] += timing.seconds is not None
        if limit and counts["threads"] >= limit:
            break
    return {
        "counts": dict(counts),
        "group_issue_counts": dict(issues),
        "note": "Order groups are candidates, not verified complete consultations. No scores.",
    }


async def smoke():
    provider = QwenProvider(QwenConfig.from_env())
    result = await provider.complete("Reply with exactly OK.", "Synthetic connectivity test.")
    print(
        json.dumps(
            {
                "status": "connected",
                "model": provider.config.model,
                "expected_reply": result.strip() == "OK",
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("preview-data", help="Local read only; no model requests")
    data.add_argument("path", type=Path)
    data.add_argument("--limit", type=int, default=10, help="0 scans all threads")
    data.add_argument("--timezone", default="Asia/Shanghai")
    commands.add_parser("qwen-smoke", help="One paid API request containing only synthetic text")
    imported = commands.add_parser(
        "import-local", help="Save raw order groups locally; no model calls"
    )
    imported.add_argument("path", type=Path)
    imported.add_argument("--limit", type=int, default=10)
    commands.add_parser("worker-once", help="Claim one queued synthetic run and call Qwen")
    commands.add_parser("recover-local", help="Mark interrupted runs; stop workers before running")
    skills = commands.add_parser("validate-skills", help="Validate metric Skill packages locally")
    skills.add_argument("path", type=Path)
    skills.add_argument(
        "--require-complete", action="store_true", help="Require all 18 published Skills"
    )
    args = parser.parse_args()
    if args.command == "preview-data":
        print(
            json.dumps(preview(args.path, args.limit, args.timezone), ensure_ascii=False, indent=2)
        )
    elif args.command == "qwen-smoke":
        asyncio.run(smoke())
    elif args.command == "validate-skills":
        from app.skills.catalog import snapshot

        if not args.path.is_dir():
            parser.error("Skill package root directory does not exist")
        rubric = snapshot(args.path)
        configured = [
            m["metric_id"] for m in rubric["metrics"] if m["scoring_status"] == "configured"
        ]
        supplied = [m["metric_id"] for m in rubric["metrics"] if m.get("skill")]
        print(
            json.dumps(
                {
                    "version": rubric["version"],
                    "supplied": supplied,
                    "published": configured,
                    "expected_count": 18,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not supplied:
            parser.error("No metric.yaml packages found one level below the root")
        if args.require_complete and len(configured) != 18:
            parser.error("All 18 published Skill packages are required")
    else:
        store = LocalJobStore(Path(os.getenv("LOCAL_JOB_DB", "data/local/jobs.sqlite3")))
        if args.command == "recover-local":
            print(json.dumps({"interrupted": store.recover_interrupted()}))
        elif args.command == "worker-once":
            from app.agents.structured import StructuredEvaluation
            from app.application.local_worker import run_one

            engine = StructuredEvaluation(QwenProvider(QwenConfig.from_env()))
            print(json.dumps({"processed": asyncio.run(run_one(store, engine))}))
        else:
            if args.limit < 0:
                parser.error("limit must be nonnegative")
            count = 0
            for index, thread in enumerate(iter_threads(args.path), 1):
                messages = normalize_thread(thread, "hxq-export")
                rounds = split_rounds(
                    messages, stable_ref("hxq-export", str(thread["chat_session_id"]))
                )
                for round_ in rounds:
                    data = json.loads(
                        json.dumps(asdict(round_), default=lambda value: value.isoformat())
                    )
                    store.save_round(round_.round_id, "raw_local", data)
                    count += 1
                if args.limit and index >= args.limit:
                    break
            print(json.dumps({"saved_order_candidates": count, "model_calls": 0}))


if __name__ == "__main__":
    main()
