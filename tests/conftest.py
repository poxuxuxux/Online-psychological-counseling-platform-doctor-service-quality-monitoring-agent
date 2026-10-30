# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import yaml

from app.config import Settings
from app.domain.models import Session
from app.infrastructure.repository import Repository
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.workflow.service import EvaluationService


@pytest.fixture
def session():
    return Session(
        session_id="s1",
        patient_id="p1",
        doctor_id="d1",
        history_complete=True,
        observation_complete=True,
        session_time=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            {"message_id": "m0", "sequence": 0, "role": "patient", "content": "我最近很难过。"},
            {
                "message_id": "m1",
                "sequence": 1,
                "role": "doctor",
                "content": "听起来你很难受，我们一起看看。",
            },
        ],
    )


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "skills"
    for dimension in ("D1", "D2"):
        folder = root / (dimension + ".1")
        folder.mkdir(parents=True)
        spec = {
            "schema_version": "1.0",
            "metric_id": dimension + ".1",
            "name": dimension,
            "definition": "Test doctor's observable response",
            "version": "1.0.0",
            "status": "published",
            "owner": "test",
            "score_values": [1, 2, 3, 4, 5],
            "anchors": [{"score": i, "criteria": str(i)} for i in range(1, 6)],
            "applicability": {"applicable_when": ["doctor response"]},
            "manual_review": [{"rule_id": "source_incomplete", "condition": "missing source"}],
            "evidence": {"allowed_sources": ["current_dialogue"]},
            "required_tools": ["evidence_locator"],
        }
        (folder / "SKILL.md").write_text(
            "---\n" + yaml.safe_dump(spec) + "---\n"
            "Evaluate source-grounded behavior.\n", encoding="utf-8"
        )
    return SkillCatalog(root)


class ScriptedModel:
    """Deterministic model double exercising real graph/tools/storage, not a production fallback."""

    configured = True

    def __init__(self, collaboration=False, conflict=False, invalid_checks=False):
        self.collaboration, self.conflict = collaboration, conflict
        self.invalid_checks = invalid_checks
        self.payloads = []

    @staticmethod
    def action(name, **arguments):
        return {
            "rationale": "Test decision based on current observation",
            "tool_call": {"name": name, "arguments": arguments},
        }

    async def json(self, system, payload, schema):
        self.payloads.append(payload)
        if payload.get("purpose") == "evidence_validation":
            return {
                "checks": [
                    {
                        "finding_id": f["finding_id"],
                        "support_status": "supported",
                        "applicability_status": "matched",
                        "rubric_status": "matched",
                        "issues": [],
                        "claim_results": []
                        if self.invalid_checks
                        else [
                            {
                                "claim_index": i,
                                "status": "supported",
                                "rationale": "Source supports claim",
                            }
                            for i, _ in enumerate(f["claims"])
                        ],
                    }
                    for f in payload["findings"]
                ]
            }
        task = payload["task"]
        obs = task["observations"]
        tools = [o["tool"] for o in obs]
        if not task["skills_read"]:
            return self.action("read_skill")
        if "dialogue" not in payload:
            return self.action("get_dialogue")
        dialogue = payload["dialogue"]["messages"]
        doctor = next(m for m in dialogue if m["role"] == "doctor" and m["content"])
        if task["kind"] == "team_lead":
            if task["phase"] == "detect":
                return self.action(
                    "assess_conflicts",
                    reason="Compared all findings against the current dialogue",
                    conflicts=[{
                        "metric_ids": ["D1.1", "D2.1"],
                        "reason": "Opposite assertions about the same doctor response",
                        "evidence_ids": payload["evidence"]["sample_ids"][:1],
                    }] if self.conflict else [],
                )
            return self.action(
                "submit_review",
                decision="revise",
                reason="Inspect source and correct claims",
                evidence_ids=payload["evidence"]["sample_ids"][:1],
            )
        if payload["inbox_pending_count"]:
            received = [o["result"] for o in obs if o["tool"] == "get_messages"]
            acked = {
                o["result"].get("message_id") for o in obs if o["tool"] == "acknowledge_message"
            }
            unacked = [m for group in received for m in group if m["message_id"] not in acked]
            if unacked:
                return self.action(
                    "acknowledge_message",
                    message_id=unacked[0]["message_id"],
                    disposition="used",
                    reason="Rechecked current source; will revise",
                )
            return self.action("get_messages")
        shared = [o["result"] for o in obs if o["tool"] == "share_evidence"]
        if not shared:
            return self.action(
                "share_evidence",
                message_id=doctor["message_id"],
                speaker="doctor",
                quote=doctor["content"][:12],
                related_indicators=task["metric_ids"],
            )
        should_revise = "acknowledge_message" in tools and all(
            f["revision_count"] == 0 for f in task["findings"].values()
        )
        if not task["findings"] or should_revise:
            evidence_id = shared[0]["evidence_id"]
            polarity = (
                "absent"
                if self.conflict and task["dimension_id"] == "D2" and not should_revise
                else "present"
            )
            return self.action(
                "submit_evaluation",
                findings=[
                    {
                        "metric_id": mid,
                        "status": "EVALUATED",
                        "score": 4 if should_revise else 5,
                        "reason": "Doctor responds to stated experience",
                        "evidence_ids": [evidence_id],
                        "claims": [
                            {
                                "behavior": "respond" if self.conflict else task["dimension_id"],
                                "subject": "doctor",
                                "polarity": polarity,
                                "scope": "current_session",
                                "statement": "Doctor responds to patient",
                                "evidence_ids": [evidence_id],
                            }
                        ],
                        "review_rule_ids": [],
                        "risk": "none",
                    }
                    for mid in task["metric_ids"]
                ],
            )
        if self.collaboration and task["dimension_id"] == "D1" and "send_message" not in tools:
            if "get_evidence" not in tools:
                return self.action("get_evidence")  # D2 finishes before this late message.
            return self.action(
                "send_message",
                receiver="evaluator:D2",
                message_type="EVIDENCE_SHARE",
                content="Please recheck source for your metric",
                evidence_ids=[shared[0]["evidence_id"]],
                related_indicators=["D2.1"],
            )
        return self.action("finish")


@pytest.fixture
def make_service(tmp_path, catalog):
    async def factory(model=None, **overrides):
        settings = replace(
            Settings(),
            database_url="sqlite:///" + str(tmp_path / "teams.sqlite3"),
            seed_demo=False,
            **overrides,
        )
        repo = Repository(settings.database_url)
        await repo.initialize()
        service = EvaluationService(
            settings, repo, model or ScriptedModel(), catalog, SkillKnowledgeSource(catalog)
        )
        return service, repo

    return factory
