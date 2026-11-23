"""Durable, capability-protected uploaded evaluations; HTTP polling never owns execution."""
import asyncio
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.domain.models import Session
from app.infrastructure.repository import Repository
from app.rubrics.catalog import SkillKnowledgeSource
from app.workflow.service import EvaluationService

router = APIRouter()
log = logging.getLogger(__name__)


class GuestJobs:
    def __init__(self, container):
        self.container = container
        db = container.settings.database_url
        parent = Path(db.removeprefix("sqlite:///")).parent if db.startswith("sqlite:///") else Path("data/local")
        self.root = parent / "guest-jobs"
        self.tasks = {}
        self.errors = {}
        self.slots = asyncio.Semaphore(2)

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    def metadata(self, job_id, token):
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise HTTPException(404, "Job not found")
        path = self.root / job_id / "access.json"
        if not path.exists():
            raise HTTPException(404, "Job not found")
        meta = json.loads(path.read_text(encoding="utf-8"))
        if not secrets.compare_digest(meta["digest"], hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(404, "Job not found")
        return meta

    async def service(self, job_id):
        c = self.container
        repo = Repository("sqlite:///" + str((self.root / job_id / "run.sqlite3").resolve()))
        await repo.initialize()
        return EvaluationService(c.settings, repo, c.model, c.catalog, SkillKnowledgeSource(c.catalog))

    def start(self, job_id, service, run_id):
        if job_id in self.tasks and not self.tasks[job_id].done():
            return

        async def work():
            try:
                async with self.slots:
                    await service.execute(run_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - expose types, never dialogue or credentials
                self.errors[job_id] = type(exc).__name__
                log.warning("Guest job failed: job=%s type=%s", job_id, type(exc).__name__)

        self.errors.pop(job_id, None)
        self.tasks[job_id] = asyncio.create_task(work(), name="guest-" + job_id)


@router.post("/api/v1/guest/jobs", status_code=202)
async def create_job(session: Session, request: Request):
    from app.api.routes import _guest_lock, _guest_requests

    manager = request.app.state.guest_jobs
    if not manager.container.model.configured:
        raise HTTPException(503, "Model not configured")
    if session.source_id == "synthetic-demo" or len(session.model_dump_json()) > 2_000_000:
        raise HTTPException(422, "Invalid guest upload")
    async with _guest_lock:
        current = time.monotonic()
        _guest_requests[:] = [t for t in _guest_requests if current - t < 3600]
        if len(_guest_requests) >= 60 or sum(not t.done() for t in manager.tasks.values()) >= 8:
            raise HTTPException(429, "Guest capacity reached")
        _guest_requests.append(current)
    job_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
    folder = manager.root / job_id
    folder.mkdir(parents=True, exist_ok=False)
    service = await manager.service(job_id)
    run_id = await service.create(session.model_copy(update={"source_id": "guest-upload"}))
    meta = {"run_id": run_id, "digest": hashlib.sha256(token.encode()).hexdigest()}
    (folder / "access.json").write_text(json.dumps(meta), encoding="utf-8")
    manager.start(job_id, service, run_id)
    return {"job_id": job_id, "token": token}


@router.get("/api/v1/guest/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    manager = request.app.state.guest_jobs
    meta = manager.metadata(job_id, request.headers.get("X-Guest-Token", ""))
    service = await manager.service(job_id)
    state = await service.repository.get_run(meta["run_id"])
    task = manager.tasks.get(job_id)
    report = state.get("report") if state.get("next_stage") == "done" else None
    if report:
        report.get("team", {}).pop("audit_url", None)
    team = state.get("team", {})
    status = "completed" if report else "running" if task and not task.done() else "interrupted"
    usage = state.get("model_usage", [])
    rejected = [e for e in team.get("events", []) if e.get("action") == "submission_rejected"]
    return {"job_id": job_id, "status": status, "stage": team.get("phase", state.get("next_stage", "pending")),
            "model_calls": team.get("model_calls", 0), "elapsed_seconds": state.get("elapsed_seconds", 0),
            "rejection_count": len(rejected),
            "last_rejection": rejected[-1]["detail"] if rejected else None,
            "agents": [{"agent_id": a, "status": t.get("status"), "error": t.get("error"),
                        "model_seconds": t.get("model_seconds", 0)} for a, t in team.get("tasks", {}).items()],
            "requests": [{"stage": u.get("purpose"), "seconds": u.get("seconds"),
                          "usage_reported": u.get("usage_reported", False)} for u in usage],
            "error": manager.errors.get(job_id), "report": report}


@router.post("/api/v1/guest/jobs/{job_id}/resume", status_code=202)
async def resume_job(job_id: str, request: Request):
    manager = request.app.state.guest_jobs
    meta = manager.metadata(job_id, request.headers.get("X-Guest-Token", ""))
    current = manager.tasks.get(job_id)
    if (not current or current.done()) and sum(not t.done() for t in manager.tasks.values()) >= 8:
        raise HTTPException(429, "Guest capacity reached")
    service = await manager.service(job_id)
    manager.start(job_id, service, meta["run_id"])
    return {"job_id": job_id}
