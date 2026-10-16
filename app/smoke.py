"""Explicit live Qwen end-to-end test with a server-generated synthetic session only."""

import asyncio
import json
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agents.structured import StructuredEvaluation
from app.api.local_backend import create_app
from app.application.local_worker import run_one
from app.infrastructure.llm.qwen import QwenConfig, QwenProvider
from app.infrastructure.repositories.local_jobs import LocalJobStore


def main():
    store = LocalJobStore(Path("data/local") / f"smoke-{uuid4()}.sqlite3")
    token = secrets.token_urlsafe(32)
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "synthetic-smoke"}
    with TestClient(create_app(store, token)) as client:
        response = client.post("/api/v1/rounds/demo", headers=headers)
        response.raise_for_status()
        response = client.post(
            "/api/v1/evaluation-runs",
            headers=headers,
            json={"round_id": response.json()["round_id"]},
        )
        response.raise_for_status()
        run_id = response.json()["run_id"]
        print(json.dumps({"stage": "queued", "run_id": run_id}), flush=True)
        asyncio.run(run_one(store, StructuredEvaluation(QwenProvider(QwenConfig.from_env()))))
        response = client.get(f"/api/v1/evaluation-runs/{run_id}/report", headers=headers)
        response.raise_for_status()
        report = response.json()
        findings = [f for r in report["agent_results"] for f in r["findings"]]
        result = {
            "stage": "report_read",
            "run_id": run_id,
            "status": report["status"],
            "agent_statuses": {r["agent_id"]: r["status"] for r in report["agent_results"]},
            "findings": len(findings),
            "checks": len(report["checks"]),
            "semantic_failures": sum(
                c["reason"] == "semantic_verification_failed" for c in report["checks"]
            ),
            "unresolved_metrics": report.get("unresolved_metrics", []),
            "re_evaluated_metrics": len(report.get("re_evaluation_attempts", {})),
            "management_status": report.get("management", {}).get("status"),
            "summary_status": report.get("summary_status"),
            "communication_records": report.get("communication_record_count"),
            "database": str(store.path),
        }
        print(json.dumps(result), flush=True)
        cursor, record_count = 0, 0
        while True:
            page = client.get(
                f"/api/v1/evaluation-runs/{run_id}/communication",
                params={"after_sequence": cursor, "limit": 50},
                headers=headers,
            )
            page.raise_for_status()
            payload = page.json()
            if not payload["records"]:
                break
            if any(record["run_id"] != run_id for record in payload["records"]):
                raise SystemExit("Communication pool scope mismatch")
            record_count += len(payload["records"])
            cursor = payload["next_sequence"]
        if record_count != result["communication_records"]:
            raise SystemExit("Communication pool persistence mismatch")
        if (
            len(findings) != 18
            or len(report["checks"]) != 18
            or any(r["status"] != "completed" for r in report["agent_results"])
            or result["semantic_failures"]
            or result["management_status"] != "completed"
            or result["summary_status"] != "completed"
        ):
            raise SystemExit("Live workflow did not pass completeness checks")


if __name__ == "__main__":
    main()
