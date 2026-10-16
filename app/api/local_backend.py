"""Separate authenticated local API. Existing Railway demo routes remain untouched."""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.evaluations import build_demo_session
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import snapshot


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    round_id: str = Field(min_length=1, max_length=200)
    rubric_version: str | None = None


def create_app(store: LocalJobStore | None = None, token: str | None = None) -> FastAPI:
    token = token if token is not None else os.getenv("LOCAL_API_TOKEN", "")
    if len(token) < 24:
        raise ValueError("Set LOCAL_API_TOKEN to a random value of at least 24 characters")
    store = store or LocalJobStore(Path(os.getenv("LOCAL_JOB_DB", "data/local/jobs.sqlite3")))

    def authorize(authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, detail={"code": "unauthorized"})

    api = FastAPI(title="心衡本地后端联调", dependencies=[Depends(authorize)])

    @api.get("/api/v1/rubrics/{version}")
    def rubric(version: str):
        current = snapshot()
        if version not in ("current", current["version"]):
            raise HTTPException(404, detail={"code": "rubric_not_found"})
        return current

    @api.post("/api/v1/rounds/demo", status_code=201)
    def seed():
        session = build_demo_session()
        session.session_id += "-tools-v1"
        store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
        return {"round_id": session.session_id, "source_kind": "server_synthetic"}

    @api.post("/api/v1/rounds/demo-follow-up", status_code=201)
    def seed_follow_up():
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
        return {
            "round_id": current.session_id,
            "previous_round_id": previous.session_id,
            "source_kind": "server_synthetic",
        }

    @api.get("/api/v1/rounds")
    def rounds(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": store.list_rounds(limit, offset)}

    @api.get("/api/v1/rounds/{round_id}")
    def detail(round_id: str):
        try:
            return store.round(round_id)
        except KeyError:
            raise HTTPException(404, detail={"code": "round_not_found"}) from None

    @api.post("/api/v1/evaluation-runs", status_code=202)
    def create(body: CreateRun, idempotency_key: str = Header(min_length=1, max_length=128)):
        current = snapshot()
        if body.rubric_version is not None and body.rubric_version != current["version"]:
            raise HTTPException(422, detail={"code": "unsupported_rubric_version"})
        try:
            run_id = store.enqueue(body.round_id, idempotency_key, current)
            return {"run_id": run_id, "status": store.job(run_id)["status"]}
        except KeyError:
            raise HTTPException(404, detail={"code": "round_not_found"}) from None
        except ValueError as error:
            raise HTTPException(409, detail={"code": str(error)}) from None

    @api.get("/api/v1/evaluation-runs/{run_id}")
    def status(run_id: str):
        try:
            job = store.job(run_id)
            return {key: value for key, value in job.items() if key != "report"}
        except KeyError:
            raise HTTPException(404, detail={"code": "job_not_found"}) from None

    @api.get("/api/v1/evaluation-runs/{run_id}/report")
    def report(run_id: str):
        try:
            job = store.job(run_id)
        except KeyError:
            raise HTTPException(404, detail={"code": "job_not_found"}) from None
        if job["report"] is None:
            raise HTTPException(409, detail={"code": "report_not_ready", "status": job["status"]})
        return job["report"]

    @api.get("/api/v1/evaluation-runs/{run_id}/communication")
    def communication(
        run_id: str, after_sequence: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)
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

    return api
