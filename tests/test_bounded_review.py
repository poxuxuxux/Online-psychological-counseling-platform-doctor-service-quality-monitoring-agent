import json

import pytest

from app.agents.structured import StructuredEvaluation
from app.api.v1.evaluations import build_demo_session
from tests.test_local_backend import FakeProvider


class ReviewProvider(FakeProvider):
    def __init__(self, mode="semantic", still_disputed=False):
        super().__init__()
        self.review_mode = mode
        self.still_disputed = still_disputed
        self.evaluated = []
        self.arbitrations = 0
        self.verifications = 0

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
        if "metrics" in payload:
            ids = [m["metric_id"] for m in payload["metrics"]]
            revised = bool(payload.get("revision_requests"))
            self.evaluated.append((ids, revised))
            if revised and self.review_mode == "bad_revision":
                return "{}"
            output = json.loads(await super().complete(system_prompt, user_prompt))
            if self.review_mode == "reference" and not revised:
                for finding in output["findings"]:
                    if finding["metric_id"] == "D4.1":
                        finding["evidence"][0]["message_ids"] = ["nonexistent"]
            return json.dumps(output)
        if "conflicts" in payload:
            self.arbitrations += 1
            if self.review_mode == "bad_arbiter":
                return json.dumps(
                    {
                        "recommendations": [
                            {
                                "metric_id": "D1.1",
                                "action": "re_evaluate",
                                "rationale": "outside assigned dispute",
                            }
                        ]
                    }
                )
            return json.dumps(
                {
                    "recommendations": [
                        {
                            "metric_id": c["metric_id"],
                            "action": "manual_review"
                            if self.review_mode == "manual"
                            else "re_evaluate",
                            "rationale": "检查完整语境",
                        }
                        for c in payload["conflicts"]
                    ]
                }
            )
        self.verifications += 1
        output = json.loads(await super().complete(system_prompt, user_prompt))
        if self.review_mode != "reference":
            for check in output["checks"]:
                if check["metric_id"] == "D4.1" and (
                    self.verifications == 1 or self.still_disputed
                ):
                    check.update(status="unsupported", reason="需要核对上下文")
        return json.dumps(output)


async def execute(provider):
    events = []
    report = await StructuredEvaluation(provider).run(
        build_demo_session(), lambda stage, data: events.append((stage, data))
    )
    return report, events


async def test_semantic_conflict_arbitrates_before_one_metric_re_evaluation():
    provider = ReviewProvider()
    report, events = await execute(provider)
    assert provider.arbitrations == 1
    assert [ids for ids, revised in provider.evaluated if revised] == [["D4.1"]]
    assert report["re_evaluation_attempts"] == {"D4.1": 1}
    assert report["unresolved_metrics"] == []
    history = [f for f in report["finding_history"] if f["metric_id"] == "D4.1"]
    assert len(history) == 2
    assert history[1]["attempt"] == 1
    assert history[1]["supersedes_finding_id"] == history[0]["finding_id"]
    assert report["adopted_findings"]["D4.1"] == history[1]["finding_id"]
    assert len(report["verification_history"]) == 19
    stages = [s for s, _ in events]
    assert (
        stages.index("arbitrating") < stages.index("re_evaluating") < stages.index("re_verifying")
    )


async def test_reference_errors_repair_without_unnecessary_arbitration():
    provider = ReviewProvider("reference")
    report, _ = await execute(provider)
    assert provider.arbitrations == 0
    assert report["unresolved_metrics"] == []
    assert report["re_evaluation_attempts"] == {"D4.1": 1}


async def test_persistent_dispute_keeps_original_and_never_loops():
    provider = ReviewProvider(still_disputed=True)
    report, _ = await execute(provider)
    assert provider.arbitrations == 1
    assert len([r for _, r in provider.evaluated if r]) == 1
    assert report["unresolved_metrics"] == ["D4.1"]
    history = [f for f in report["finding_history"] if f["metric_id"] == "D4.1"]
    assert report["adopted_findings"]["D4.1"] == history[0]["finding_id"]
    assert report["checks"][9]["finding_id"] in {f["finding_id"] for f in report["finding_history"]}


@pytest.mark.parametrize("mode", ["manual", "bad_arbiter"])
async def test_manual_or_out_of_scope_arbitration_cannot_dispatch(mode):
    provider = ReviewProvider(mode)
    report, _ = await execute(provider)
    assert not report["re_evaluation_attempts"]
    assert report["unresolved_metrics"] == ["D4.1"]
    assert not any(revised for _, revised in provider.evaluated)


async def test_failed_revision_consumes_budget_and_retains_initial_version():
    provider = ReviewProvider("bad_revision")
    report, _ = await execute(provider)
    assert report["re_evaluation_failures"] == ["D4.1"]
    assert report["re_evaluation_attempts"] == {"D4.1": 1}
    assert len(report["finding_history"]) == 18
    assert report["unresolved_metrics"] == ["D4.1"]
