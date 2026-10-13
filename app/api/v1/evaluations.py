"""功能：提供比赛演示会话与单轮评价接口。"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request

from app.domain.models import ConversationSession, EvaluationReport, Message
from app.evaluation.analytics import build_overview, statistics_period

router = APIRouter(prefix="/api/v1")


def build_demo_session() -> ConversationSession:
    """返回不含真实个人信息的固定合成咨询轮次。"""
    started_at = datetime(2026, 10, 11, 14, 0, 0)
    rows = (
        ("patient", "医生您好，我最近两周晚上很难入睡，白天上班也很疲惫。"),
        ("doctor", "听起来这段时间的失眠让你很辛苦。我想先了解一下，通常几点入睡，夜里会醒几次？"),
        ("patient", "大约凌晨一点才能睡，夜里会醒两三次，第二天很难集中注意力。"),
        (
            "doctor",
            "谢谢你说得这么具体。我们可以先记录一周的睡眠情况，下次根据记录一起讨论调整方案。",
        ),
        ("patient", "好的，我愿意试试。"),
        ("doctor", "如果这几天症状明显加重，或已经影响到基本生活，请及时联系专业医疗机构。"),
    )
    messages = [
        Message(
            message_id=f"demo-m{index + 1:02d}",
            role=role,  # type: ignore[arg-type]
            content=content,
            sequence=index,
            timestamp=started_at + timedelta(minutes=index * 2),
        )
        for index, (role, content) in enumerate(rows)
    ]
    return ConversationSession(
        session_id="demo-order-20261011-001",
        source_id="synthetic-demo",
        anonymized_patient_ref="demo-patient-001",
        consultation_round="initial",
        messages=messages,
        imported_at=started_at,
    )


@router.get("/demo/session", response_model=ConversationSession)
async def get_demo_session() -> ConversationSession:
    """取得评委体验使用的合成数据。"""
    return build_demo_session()


@router.post("/evaluations", response_model=EvaluationReport)
async def evaluate_session(session: ConversationSession, request: Request) -> EvaluationReport:
    """保存本次会话并执行预处理、三 Agent 评价和证据定位。"""
    if session.source_id != "synthetic-demo":
        raise HTTPException(
            status_code=400,
            detail="当前公开演示仅接收仓库内置的合成数据。",
        )
    container = request.app.state.container
    await container.session_repository.save(session)
    await container.evaluation_store.save_session(session)
    report = await container.evaluate_session.execute(session)
    await container.evaluation_store.save_report(report)
    return report


@router.get("/evaluations/recent")
async def recent_evaluations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    """读取 PostgreSQL 中最近的演示报告摘要。"""
    container = request.app.state.container
    return {
        "database_configured": container.evaluation_store.configured,
        "items": await container.evaluation_store.recent_reports(limit),
    }


@router.get("/evaluations/overview")
async def evaluation_overview(request: Request, days: int = Query(default=30, ge=1, le=90)) -> dict:
    """Aggregate stored reports without returning identities, evidence or conversation text."""
    store = request.app.state.container.evaluation_store
    now = datetime.now(UTC)
    if not store.configured:
        return build_overview([], days, now, available=False)
    start, end = statistics_period(days, now)
    try:
        records = await store.overview_records(start, end)
    except Exception as error:
        raise HTTPException(status_code=503, detail="统计数据暂时不可用，请稍后重试。") from error
    return build_overview(records, days, now)


@router.get("/consultations")
async def list_consultations(
    request: Request,
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100000),
    query: str = Query(default="", max_length=120),
) -> dict:
    """分页读取数据库中的合成咨询 ID，未评价的咨询也进入列表。"""
    try:
        return await request.app.state.container.evaluation_store.list_consultations(
            limit, offset, query.strip()
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail="咨询列表暂时不可用，请稍后重试。") from error


@router.get("/consultations/{session_id}")
async def consultation_detail(request: Request, session_id: str) -> dict:
    """读取指定合成咨询及其最新报告；真实数据接入须沿用平台访问控制。"""
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=422, detail="咨询 ID 格式不正确。")
    try:
        detail = await request.app.state.container.evaluation_store.consultation_detail(session_id)
    except Exception as error:
        raise HTTPException(status_code=503, detail="咨询记录暂时不可用，请稍后重试。") from error
    if detail is None:
        raise HTTPException(status_code=404, detail="咨询记录不存在或不在当前演示范围。")
    return detail
