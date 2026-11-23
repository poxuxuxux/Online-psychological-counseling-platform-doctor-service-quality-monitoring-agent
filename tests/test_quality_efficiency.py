# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
import json

from app.domain.ports import ModelUnavailable
from app.rubrics.payload import metric_payload
from tests.conftest import ScriptedModel


async def test_provider_errors_stop_after_two_attempts_per_agent(make_service, session):
    class FailedModel(ScriptedModel):
        async def json(self, *args):
            raise ModelUnavailable("model_timeout")

    service, repo = await make_service(FailedModel())
    report = await service.evaluate(session)
    state = await repo.get_run(report["evaluation_id"])
    assert state["team"]["model_calls"] == 4
    assert all(t["model_errors"] == 2 for t in state["team"]["tasks"].values())


def test_projection_preserves_rules_and_instructions(catalog):
    spec = catalog.metrics["D1.1"]
    projection = metric_payload(spec)
    assert projection["anchors"] == spec["anchors"]
    assert projection["manual_review"] == spec["manual_review"]
    # read_skill 只返回投影：SKILL.md 正文（instructions）必须保留，Agent 才能读到完整指引。
    assert projection["instructions"] == spec["instructions"]
    assert "configuration_issues" not in projection
    assert len(json.dumps(projection)) < len(json.dumps(spec))
