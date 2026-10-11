"""功能：验证可信评价链的数据契约能够区分事实、反证、证据不足和修正版本。"""

from app.domain.models import (
    AgentResult,
    ClaimVerification,
    EvaluationReport,
    EvidenceVerificationResult,
    FactClaim,
    Finding,
)


def test_fact_verification_distinguishes_contradiction_from_insufficient_evidence():
    finding = Finding(metric_id="D4.1", metric_version="1.0.0", rationale="医生充分回应焦虑")
    supported = FactClaim(
        finding_id=finding.finding_id,
        claim_type="observed_behavior",
        statement="医生询问了睡眠情况",
        subject_role="doctor",
        behavior="询问",
        object_text="睡眠情况",
    )
    insufficient = FactClaim(
        finding_id=finding.finding_id,
        claim_type="score_basis",
        statement="该询问充分回应了患者的工作焦虑",
        subject_role="doctor",
    )

    verification = EvidenceVerificationResult(
        finding_id=finding.finding_id,
        reference_status="valid",
        claims=[supported, insufficient],
        claim_results=[
            ClaimVerification(claim_id=supported.claim_id, status="supported"),
            ClaimVerification(
                claim_id=insufficient.claim_id,
                status="insufficient_evidence",
            ),
        ],
        applicability_status="matched",
        rubric_status="mismatched",
        support_status="partial",
        revision_request="保留询问睡眠的事实，收窄充分回应工作焦虑的评价。",
    )

    assert verification.claim_results[0].status == "supported"
    assert verification.claim_results[1].status == "insufficient_evidence"
    assert verification.rubric_status == "mismatched"


def test_revised_finding_links_to_initial_finding():
    initial = Finding(metric_id="D4.1", rationale="初评")
    revised = Finding(
        metric_id="D4.1",
        rationale="修正后评价",
        attempt=1,
        supersedes_finding_id=initial.finding_id,
    )

    assert revised.supersedes_finding_id == initial.finding_id
    assert revised.finding_id != initial.finding_id


def test_report_preserves_structured_verification_results():
    finding = Finding(metric_id="D4.1", rationale="待核验")
    verification = EvidenceVerificationResult(
        finding_id=finding.finding_id,
        reference_status="valid",
        applicability_status="matched",
        rubric_status="uncertain",
        support_status="uncertain",
        reference_conflict=True,
    )
    report = EvaluationReport(
        evaluation_id="eval-1",
        session_id="session-1",
        status="partial",
        agent_results=[AgentResult(agent_id="empathy_relationship", status="completed", findings=[finding])],
        verification_results=[verification],
    )

    assert report.verification_results[0].finding_id == finding.finding_id
    assert report.verification_results[0].reference_conflict is True
