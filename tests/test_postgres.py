# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
"""Run against a disposable PostgreSQL service, never against the production DATABASE_URL."""

import os
from dataclasses import replace

import pytest

from app.config import Settings
from app.infrastructure.repository import Repository
from app.rubrics.catalog import SkillKnowledgeSource
from app.workflow.service import EvaluationService
from tests.conftest import ScriptedModel


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL not configured"
)
async def test_postgres_transactional_team_and_history(catalog, session):
    settings = replace(
        Settings(), database_url=os.environ.get("TEST_DATABASE_URL", ""), seed_demo=False
    )
    repo = Repository(settings.database_url)
    await repo.initialize()
    from app.domain.models import uid

    session = session.model_copy(update={"session_id": uid("pg"), "patient_id": uid("patient")})
    service = EvaluationService(
        settings, repo, ScriptedModel(collaboration=True), catalog, SkillKnowledgeSource(catalog)
    )
    report = await service.evaluate(session)
    assert report["quality_profile"]["overall_score"] == 4.5
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["messages"][0]["status"] == "PROCESSED"
    assert (await repo.readiness())["connected"]
