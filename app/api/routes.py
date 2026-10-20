# 环节：API 接入层；用途：定义 HTTP 路由、鉴权及请求响应处理。
import secrets

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from app.demo import sessions
from app.domain.models import Session, StrictModel, now, uid
from app.infrastructure.repository import RunBusy

router = APIRouter()


def authorized(request):
    expected = request.app.state.container.settings.api_token
    provided = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return bool(len(expected) >= 24 and secrets.compare_digest(provided, expected))


def require_auth(request):
    if not authorized(request):
        raise HTTPException(401, "A configured EVALUATION_API_TOKEN is required for private data")


async def checked_run(request, run_id):
    state = await request.app.state.container.repository.get_run(run_id)
    if not state:
        raise HTTPException(404, "Run not found")
    if state["session"].get("source_id") != "synthetic-demo":
        require_auth(request)
    return state


def check_input(request, session):
    # Public synthetic calls must exactly match server fixtures, not merely claim the source label.
    canonical = next((s for s in sessions() if s.session_id == session.session_id), None)
    from app.context.service import preprocess

    if canonical and preprocess(canonical) == preprocess(session):
        return
    require_auth(request)
    if session.source_id == "synthetic-demo":
        raise HTTPException(422, "Reserved synthetic-demo source cannot contain custom data")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    c = request.app.state.container
    database = await c.repository.readiness()
    bucket = database.get("bucket", {})
    connected = database["connected"] and (
        not bucket.get("configured") or bucket.get("connected") is True
    )
    return JSONResponse(
        status_code=200 if connected else 503,
        content={
            "status": "ready" if connected else "not_ready",
            "database": database,
            "model": {"configured": c.model.configured},
            "skills": {
                "version": c.catalog.version,
                "dimensions": c.catalog.dimensions,
                "configuration_issues": {
                    mid: m["configuration_issues"]
                    for mid, m in c.catalog.metrics.items()
                    if m["configuration_issues"]
                },
            },
        },
    )


@router.get("/api/v1/demo/session")
async def demo_session():
    return sessions()[0]


@router.get("/api/v1/demo/sessions")
async def demo_sessions():
    return sessions()


@router.get("/api/v1/demo/sessions/{session_id}")
async def demo_detail(session_id: str, request: Request):
    session = next((s for s in sessions() if s.session_id == session_id), None)
    if session is None:
        raise HTTPException(404, "Demo session not found")
    detail = await request.app.state.container.repository.detail(session_id)
    return {"session": session, "report": detail["report"] if detail else None}


@router.post("/api/v1/sessions", status_code=201)
async def import_session(session: Session, request: Request):
    require_auth(request)
    check_input(request, session)
    from app.context.service import preprocess

    try:
        await request.app.state.container.repository.save_session(preprocess(session))
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"session_id": session.session_id}


@router.post("/api/v1/runs", status_code=201)
async def create_run(session: Session, request: Request):
    check_input(request, session)
    try:
        run_id = await request.app.state.container.service.create(session)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"run_id": run_id, "status": "pending", "execute_url": f"/api/v1/runs/{run_id}/execute"}


@router.post("/api/v1/runs/{run_id}/execute")
async def execute_run(run_id: str, request: Request):
    await checked_run(request, run_id)
    try:
        return await request.app.state.container.service.execute(run_id)
    except RunBusy:
        raise HTTPException(
            409, "Run is currently leased; retry after its worker finishes or lease expires"
        ) from None


@router.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    state = await checked_run(request, run_id)
    return {
        "run_id": run_id,
        "status": state["status"],
        "next_stage": state["next_stage"],
        "completed_stages": state["completed_stages"],
        "report": state.get("report"),
    }


@router.get("/api/v1/runs/{run_id}/audit")
async def audit(run_id: str, request: Request):
    state = await checked_run(request, run_id)
    return {
        "run_id": run_id,
        "team": state.get("team", {}),
        "completion": state.get("completion"),
        "rubric_version": state["skills"]["version"],
        "completed_stages": state["completed_stages"],
    }


@router.post("/api/v1/evaluations")
async def evaluate(session: Session, request: Request):
    check_input(request, session)
    try:
        return await request.app.state.container.service.evaluate(session)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


@router.get("/api/v1/evaluations/recent")
async def recent(request: Request, limit: int = Query(20, ge=1, le=100)):
    return {
        "database_configured": True,
        "items": await request.app.state.container.repository.recent(
            limit, not authorized(request)
        ),
    }


@router.get("/api/v1/consultations")
async def consultations(
    request: Request,
    limit: int = Query(5, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    query: str = Query("", max_length=120),
    scope: str = Query("visible", pattern="^(visible|private)$"),
):
    if scope == "private":
        require_auth(request)
    return await request.app.state.container.repository.consultations(
        limit, offset, query, not authorized(request), scope == "private"
    )


@router.get("/api/v1/consultations/{session_id}")
async def consultation(session_id: str, request: Request):
    detail = await request.app.state.container.repository.detail(session_id)
    if not detail:
        raise HTTPException(404, "Session not found")
    if detail["session"].get("source_id") != "synthetic-demo":
        require_auth(request)
    return detail


@router.get("/api/v1/evaluations/overview")
async def evaluation_overview(request: Request, days: int = Query(30, ge=1, le=90)):
    from app.evaluation.analytics import overview

    c = request.app.state.container
    records = await c.repository.latest_reports(not authorized(request))
    return overview(records, c.catalog, days, "postgresql" if c.repository.postgres else "sqlite")


class ReviewInput(StrictModel):
    evaluation_id: str
    finding_id: str
    decision: str = Field(pattern="^(确认|驳回|建议修正|无法判断|升级复核)$")
    reason: str = Field(min_length=5, max_length=2000)


@router.get("/api/v1/evaluations/{run_id}/reviews")
async def reviews(run_id: str, request: Request):
    await checked_run(request, run_id)
    return {"items": await request.app.state.container.repository.reviews(run_id)}


@router.post("/api/v1/evaluations/{run_id}/reviews", status_code=201)
async def add_review(run_id: str, payload: ReviewInput, request: Request):
    state = await checked_run(request, run_id)
    ids = {
        f["finding_id"]
        for a in state.get("report", {}).get("agent_results", [])
        for f in a["findings"]
    }
    if payload.evaluation_id != run_id or payload.finding_id not in ids:
        raise HTTPException(422, "Report/finding mismatch")
    review = {"review_id": uid("review"), **payload.model_dump(), "created_at": now()}
    await request.app.state.container.repository.add_review(review)
    return review
