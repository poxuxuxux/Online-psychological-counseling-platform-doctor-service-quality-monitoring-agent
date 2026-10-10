"""功能：验证证据核验工具的引用定位与归一化匹配。"""

from app.domain.models import (
    AgentResult,
    ConversationEvidenceRef,
    Finding,
    MediaAsset,
    TimeRange,
)
from app.evaluation.evidence_verifier import EvidenceVerifier
from tests.factories import make_message, make_session


def make_result(quote: str, message_ids=None, media_ranges=None) -> AgentResult:
    """构造带单条证据的 Agent 结果。"""
    return AgentResult(
        agent_id="empathy",
        status="completed",
        findings=[
            Finding(
                metric_id="D4",
                rationale="医生回应了患者的情绪。",
                evidence=[
                    ConversationEvidenceRef(
                        message_ids=message_ids or ["m-002"],
                        quote=quote,
                        explanation="医生承接患者表达",
                        media_time_ranges=media_ranges or [],
                    )
                ],
            )
        ],
    )


def test_valid_evidence_has_no_issues():
    session = make_session()
    issues = EvidenceVerifier().verify(make_result("听起来你已经被失眠困扰了一段时间。"), session)
    assert issues == []


def test_fullwidth_and_whitespace_quote_still_matches():
    session = make_session()
    issues = EvidenceVerifier().verify(make_result("　听起来你已经被失眠困扰了　一段时间。"), session)
    assert issues == []


def test_missing_message_id_is_flagged():
    session = make_session()
    issues = EvidenceVerifier().verify(make_result("任意文本", message_ids=["m-999"]), session)
    assert any("message ID not found" in issue for issue in issues)


def test_fabricated_quote_is_flagged():
    session = make_session()
    issues = EvidenceVerifier().verify(make_result("这段话根本不存在于会话中。"), session)
    assert any("quote does not match" in issue for issue in issues)


def test_media_range_exceeding_duration_is_flagged():
    media = MediaAsset(
        media_id="media-001", modality="audio", storage_ref="audio-001", duration_seconds=60.0
    )
    session = make_session(
        messages=[
            make_message("m-001", role="patient", content="我最近总是睡不好。", sequence=0),
            make_message(
                "m-002",
                role="doctor",
                content="听起来你已经被失眠困扰了一段时间。",
                sequence=1,
                modality="audio",
                media=media,
            ),
        ]
    )
    issues = EvidenceVerifier().verify(
        make_result("失眠", media_ranges=[TimeRange(start_seconds=0, end_seconds=120)]), session
    )
    assert any("exceeds duration" in issue for issue in issues)


def test_media_range_on_text_message_is_flagged():
    session = make_session()
    issues = EvidenceVerifier().verify(
        make_result("失眠", media_ranges=[TimeRange(start_seconds=0, end_seconds=10)]), session
    )
    assert any("non-media message" in issue for issue in issues)
