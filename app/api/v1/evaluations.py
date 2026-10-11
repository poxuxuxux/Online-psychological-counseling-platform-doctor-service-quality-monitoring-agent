"""功能：提供比赛演示会话与单轮评价接口。"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request

from app.domain.models import ConversationSession, EvaluationReport, Message

router = APIRouter(prefix="/api/v1")


def build_demo_session() -> ConversationSession:
    """返回不含真实个人信息的固定合成咨询轮次。"""
    started_at = datetime(2026, 10, 11, 14, 0, 0)
    rows = (
        ("patient", "医生您好，我最近两周晚上很难入睡，白天上班也很疲惫。"),
        ("doctor", "听起来这段时间的失眠让你很辛苦。我想先了解一下，通常几点入睡，夜里会醒几次？"),
        ("patient", "大约凌晨一点才能睡，夜里会醒两三次，第二天很难集中注意力。"),
        ("doctor", "谢谢你说得这么具体。我们可以先记录一周的睡眠情况，下次根据记录一起讨论调整方案。"),
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
    container = request.app.state.container
    await container.session_repository.save(session)
    return await container.evaluate_session.execute(session)
