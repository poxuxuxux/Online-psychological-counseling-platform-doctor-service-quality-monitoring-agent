import json
import shutil
from pathlib import Path

import pytest
import yaml

from app.agents.structured import StructuredEvaluation
from app.api.v1.evaluations import build_demo_session
from app.application.local_worker import run_one
from app.domain.models import Finding
from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.skills.catalog import snapshot
from app.skills.contracts import MetricSkillSpec
from app.skills.metric_loader import load_metric_package
from app.skills.runtime import validate_check, validate_finding
from tests.test_local_backend import FakeProvider


@pytest.fixture
def package(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/metric_skills/D4.1"
    directory = tmp_path / "packages/D4.1"
    shutil.copytree(source, directory)
    return directory


def published(package):
    data = yaml.safe_load((package / "metric.yaml").read_text(encoding="utf-8"))
    data["status"] = "published"
    data["version"] = "1.0.0"
    data["anchors"] = [
        {"score": score, "criteria": f"合成测试档位{score}；仅用于接口测试"}
        for score in range(1, 6)
    ]
    (package / "metric.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return data


def test_draft_package_is_loaded_but_not_scored(package):
    rubric = snapshot(package.parent)
    metric = next(m for m in rubric["metrics"] if m["metric_id"] == "D4.1")
    assert metric["scoring_status"] == "not_configured"
    assert metric["skill"]["spec"]["score_values"] == [1, 2, 3, 4, 5]
    assert "同一规则" in metric["skill"]["instructions"]
    assert len(rubric["metrics"]) == 18


def test_publish_requires_all_anchors_and_explicit_scale(package):
    data = load_metric_package(package)["spec"]
    data["status"] = "published"
    with pytest.raises(ValueError, match="every score anchor"):
        MetricSkillSpec.model_validate(data)
    data = published(package)
    assert MetricSkillSpec.model_validate(data).status == "published"
    data["score_values"] = [0, 1, 2, 3, 4, 5]
    with pytest.raises(ValueError, match="every score anchor"):
        MetricSkillSpec.model_validate(data)
    data["anchors"].insert(0, {"score": 0, "criteria": "合成零分规则"})
    assert MetricSkillSpec.model_validate(data).score_values[0] == 0


def test_invalid_package_never_silently_falls_back(package):
    with (package / "metric.yaml").open("a", encoding="utf-8") as stream:
        stream.write("\nversion: 9.0.0\n")
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        snapshot(package.parent)


def test_changed_instructions_change_snapshot_and_duplicate_or_wrong_owner_fail(package):
    old = snapshot(package.parent)["version"]
    with (package / "SKILL.md").open("a", encoding="utf-8") as stream:
        stream.write("\n合成新增说明。\n")
    assert snapshot(package.parent)["version"] != old
    data = published(package)
    data["owner"] = "professional_service"
    (package / "metric.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="owner"):
        snapshot(package.parent)


class SkillProvider(FakeProvider):
    def __init__(self, invalid_score=None):
        super().__init__()
        self.seen = []
        self.invalid_score = invalid_score

    async def complete(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        if payload.get("task_type") in (
            "management",
            "result_summary",
            "risk_scan",
            "response_pairing",
            "disagreement_detection",
        ):
            return await super().complete(system_prompt, user_prompt)
        definitions = payload.get("metrics", payload.get("definitions", []))
        for metric in definitions:
            if metric["metric_id"] == "D4.1":
                self.seen.append(metric["skill"]["content_hash"])
                assert metric["skill"]["spec"]["anchors"][3]["score"] == 4
                assert "同一规则" in metric["skill"]["instructions"]
        output = json.loads(await super().complete(system_prompt, user_prompt))
        if "findings" in output:
            for finding in output["findings"]:
                if finding["metric_id"] == "D4.1":
                    finding.update(
                        score=self.invalid_score if self.invalid_score is not None else 4,
                        review_rule_ids=["context_ambiguous"],
                    )
        else:
            for check in output["checks"]:
                if check["metric_id"] == "D4.1":
                    check.update(
                        applicability_status="matched",
                        rubric_status="matched",
                        review_rule_ids=["context_ambiguous"],
                    )
        return json.dumps(output)


async def test_evaluator_and_verifier_use_same_frozen_skill_and_manual_rules(package):
    published(package)
    provider = SkillProvider()
    rubric = snapshot(package.parent)
    engine = StructuredEvaluation(provider, rubric)
    (package / "SKILL.md").write_text("Changed after snapshot", encoding="utf-8")
    result = await engine.run(build_demo_session(), lambda *_: None)
    finding = next(
        f for a in result["agent_results"] for f in a["findings"] if f["metric_id"] == "D4.1"
    )
    assert finding["score"] == 4
    assert finding["metric_version"] == "1.0.0"
    assert finding["requires_manual_review"]
    assert result["review_rule_hits"]
    assert len(provider.seen) == 2 and len(set(provider.seen)) == 1
    assert result["rubric"] == rubric


@pytest.mark.parametrize("invalid_score", [0, 2.5])
async def test_one_to_five_skill_rejects_zero_and_fractional_scores(package, invalid_score):
    published(package)
    result = await StructuredEvaluation(SkillProvider(invalid_score), snapshot(package.parent)).run(
        build_demo_session(), lambda *_: None
    )
    assert (
        next(a for a in result["agent_results"] if a["agent_id"] == "empathy_relationship")[
            "status"
        ]
        == "failed"
    )


async def test_queued_job_uses_stored_skill_even_after_files_change(package, tmp_path):
    published(package)
    store = LocalJobStore(tmp_path / "jobs.sqlite3")
    session = build_demo_session()
    store.save_round(session.session_id, "server_synthetic", session.model_dump(mode="json"))
    original = snapshot(package.parent)
    job_id = store.enqueue(session.session_id, "skill-job", original)
    (package / "SKILL.md").write_text("Later edit", encoding="utf-8")
    await run_one(store, StructuredEvaluation(SkillProvider(), snapshot(package.parent)))
    assert store.job(job_id)["report"]["rubric"] == original


def test_published_skill_requires_explicit_review_and_valid_rule_ids(package):
    published(package)
    metric = next(m for m in snapshot(package.parent)["metrics"] if m["metric_id"] == "D4.1")
    with pytest.raises(ValueError, match="manual_review_rules_not_checked"):
        validate_finding(metric, Finding(metric_id="D4.1", score=4, rationale="test"))
    with pytest.raises(ValueError, match="unknown_or_duplicate_review_rule"):
        validate_finding(
            metric,
            Finding(metric_id="D4.1", score=4, rationale="test", review_rule_ids=["invented"]),
        )
    with pytest.raises(ValueError, match="nonapplicable_metric"):
        validate_finding(
            metric,
            Finding(
                metric_id="D4.1",
                applicability="not_applicable",
                score=4,
                rationale="test",
                review_rule_ids=[],
            ),
        )


def test_semantic_check_cannot_skip_published_skill_validation(package):
    published(package)
    metric = next(m for m in snapshot(package.parent)["metrics"] if m["metric_id"] == "D4.1")
    check = validate_check(metric, {"metric_id": "D4.1", "status": "supported", "reason": "test"})
    assert check["status"] == "uncertain"
    with pytest.raises(ValueError, match="unknown_verification_review_rule"):
        validate_check(metric, {"review_rule_ids": ["invented"]})


def test_same_metric_in_two_packages_fails(package):
    shutil.copytree(package, package.parent / "duplicate")
    with pytest.raises(ValueError, match="duplicate metric"):
        snapshot(package.parent)


def test_exported_json_schema_matches_contract():
    path = Path(__file__).resolve().parents[1] / "docs/contracts/metric-skill-v1.schema.json"
    assert json.loads(path.read_text(encoding="utf-8")) == MetricSkillSpec.model_json_schema()
