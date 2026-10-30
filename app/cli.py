# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
"""Local debugging commands. Live evaluation is explicit and uses configured model credentials."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from app.bootstrap import build_container
from app.domain.models import Session


async def run(args):
    container = await build_container()
    if args.command == "check":
        print(
            json.dumps(
                {
                    "database": await container.repository.readiness(),
                    "model_configured": container.model.configured,
                    "dimensions": container.catalog.dimensions,
                    "metric_count": len(container.catalog.metrics),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "evaluate":
        session = Session.model_validate_json(args.path.read_text(encoding="utf-8-sig"))
        report = await container.service.evaluate(session)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"evaluation_id": report["evaluation_id"], "status": report["status"]}))
    elif args.command == "migrate-bucket":
        print(json.dumps(await container.repository.migrate_inline_payloads()))
    elif args.command == "import-directory":
        from app.context.service import preprocess

        if not args.path.is_dir():
            raise ValueError("Import path must be an existing directory of Session JSON files")
        imported = 0
        for path in sorted(args.path.glob("*.json")):
            if path.name == "manifest.json":
                continue
            session = Session.model_validate_json(path.read_text(encoding="utf-8-sig"))
            await container.repository.save_session(preprocess(session))
            imported += 1
        if imported == 0:
            raise ValueError("No Session JSON files found for import")
        print(json.dumps({"processed_sessions": imported}))
    else:
        report = await container.service.execute(args.run_id)
        print(json.dumps({"evaluation_id": report["evaluation_id"], "status": report["status"]}))


def main():
    load_dotenv(override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("path", type=Path)
    evaluate.add_argument("--output", type=Path, default=Path("evaluation-report.json"))
    resume = commands.add_parser("resume")
    resume.add_argument("run_id")
    commands.add_parser("migrate-bucket", help="Move existing inline sessions and runs to Bucket")
    importer = commands.add_parser(
        "import-directory", help="Import normalized per-session JSON files"
    )
    importer.add_argument("path", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
