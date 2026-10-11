"""功能：验证比赛演示的合成会话可以贯穿三 Agent 与证据核验流程。"""

from app.api.v1.evaluations import build_demo_session
from app.bootstrap import build_container


async def test_demo_session_completes_three_agent_evaluation():
    container = build_container()
    report = await container.evaluate_session.execute(build_demo_session())

    assert report.status == "completed"
    assert [result.agent_id for result in report.agent_results] == [
        "professional_service",
        "process_response",
        "empathy_relationship",
    ]
    assert all(result.status == "completed" for result in report.agent_results)
    assert sum(len(result.findings) for result in report.agent_results) == 7
    assert report.limitations == []


async def test_demo_findings_only_quote_messages_from_current_session():
    container = build_container()
    session = build_demo_session()
    report = await container.evaluate_session.execute(session)
    message_ids = {message.message_id for message in session.messages}

    for result in report.agent_results:
        for finding in result.findings:
            for evidence in finding.evidence:
                assert set(evidence.message_ids) <= message_ids
