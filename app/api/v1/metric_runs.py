"""Same-origin synthetic metric evaluation API for the quality console."""

import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.evaluations import build_demo_session
from app.skills.catalog import snapshot

router = APIRouter(prefix="/api/v1", tags=["metric-runs"])


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    round_id: str = Field(min_length=1, max_length=200)
    rubric_version: str | None = None


def require_store(request: Request, access_code: str = Header(default="", alias="X-Metric-Runs-Key")):
    expected = os.getenv("METRIC_RUNS_ACCESS_CODE", "")
    if len(expected) < 24 or not hasattr(request.app.state, "metric_job_store"):
        raise HTTPException(503, detail={"code": "metric_runs_not_configured"})
    if not secrets.compare_digest(access_code, expected):
        raise HTTPException(401, detail={"code": "metric_runs_unauthorized"})
    return request.app.state.metric_job_store


@router.get("/metric-runs/capabilities")
def capabilities(request: Request):
    return {
        "enabled": len(os.getenv("METRIC_RUNS_ACCESS_CODE", "")) >= 24
        and hasattr(request.app.state, "metric_job_store"),
        "source": "server_synthetic_only",
    }


@router.get("/rubrics/current")
def current_rubric(store=Depends(require_store)):
    return snapshot()


@router.post("/rounds/demo", status_code=201)
def seed_demo(store=Depends(require_store)):
    session = build_demo_session()
    session.session_id += "-tools-v1"
    store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
    return {"round_id": session.session_id, "source_kind": "server_synthetic"}


@router.post("/rounds/demo-follow-up", status_code=201)
def seed_follow_up(store=Depends(require_store)):
    previous = build_demo_session()
    previous.session_id += "-tools-v1"
    store.save_round(previous.session_id, "server_synthetic", previous.model_dump(mode="json"))
    current = previous.model_copy(deep=True)
    current.session_id = "demo-follow-up-tools-v1"
    current.consultation_round = "follow_up"
    current.imported_at += timedelta(days=1)
    current.service_context.order_ref = "synthetic-follow-up-order"
    current.service_context.consultation_started_at += timedelta(days=1)
    for message in current.messages:
        message.message_id = "follow-up-" + message.message_id
        message.timestamp += timedelta(days=1)
    current.messages[0].content = "医生您好，我记录了这周睡眠时间，想继续讨论睡眠情况。"
    store.save_round(current.session_id, "server_synthetic", current.model_dump(mode="json"))
    return {"round_id": current.session_id, "source_kind": "server_synthetic"}


@router.get("/rounds/{round_id}")
def round_detail(round_id: str, store=Depends(require_store)):
    try:
        return store.round(round_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "round_not_found"}) from None


@router.post("/evaluation-runs", status_code=202)
def create_run(
    body: CreateRun,
    idempotency_key: str = Header(min_length=1, max_length=128),
    store=Depends(require_store),
):
    rubric = snapshot()
    if body.rubric_version is not None and body.rubric_version != rubric["version"]:
        raise HTTPException(422, detail={"code": "unsupported_rubric_version"})
    try:
        run_id = store.enqueue(body.round_id, idempotency_key, rubric)
        return {"run_id": run_id, "status": store.job(run_id)["status"]}
    except KeyError:
        raise HTTPException(404, detail={"code": "round_not_found"}) from None
    except ValueError as error:
        raise HTTPException(409, detail={"code": str(error)}) from None


@router.get("/evaluation-runs/{run_id}")
def run_status(run_id: str, store=Depends(require_store)):
    try:
        job = store.job(run_id)
        return {key: value for key, value in job.items() if key != "report"}
    except KeyError:
        raise HTTPException(404, detail={"code": "job_not_found"}) from None


@router.get("/evaluation-runs/{run_id}/report")
def run_report(run_id: str, store=Depends(require_store)):
    try:
        job = store.job(run_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "job_not_found"}) from None
    if job["report"] is None:
        raise HTTPException(409, detail={"code": "report_not_ready", "status": job["status"]})
    return job["report"]


@router.get("/evaluation-runs/{run_id}/communication")
def run_communication(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    store=Depends(require_store),
):
    try:
        store.job(run_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "job_not_found"}) from None
    records = store.pool_records(run_id, after_sequence, limit)
    return {
        "run_id": run_id,
        "records": records,
        "next_sequence": records[-1]["sequence"] if records else after_sequence,
    }
