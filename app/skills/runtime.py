"""Apply machine-checkable Skill constraints; semantic conditions remain verifier work."""

from app.domain.models import Finding
from app.skills.contracts import MetricSkillSpec


def validate_finding(metric: dict, finding: Finding, time_facts: list[dict] | None = None) -> None:
    package = metric.get("skill")
    if not package:
        if finding.score is not None:
            raise ValueError("score_without_configured_rubric")
        if finding.review_rule_ids:
            raise ValueError("review_rules_without_skill")
        finding.metric_version = "unconfigured"
        finding.limitations = sorted(set(finding.limitations + ["scoring_rules_not_configured"]))
        return
    spec = MetricSkillSpec.model_validate(package["spec"])
    finding.metric_version = spec.version
    if spec.status == "published" and "review_rule_ids" not in finding.model_fields_set:
        raise ValueError("manual_review_rules_not_checked")
    rule_ids = {rule.rule_id for rule in spec.manual_review}
    if (
        len(set(finding.review_rule_ids)) != len(finding.review_rule_ids)
        or not set(finding.review_rule_ids) <= rule_ids
    ):
        raise ValueError("unknown_or_duplicate_review_rule")
    if finding.applicability != "applicable" and finding.score is not None:
        raise ValueError("nonapplicable_metric_must_not_have_score")
    if spec.status != "published":
        if finding.score is not None:
            raise ValueError("draft_skill_must_not_score")
        finding.limitations = sorted(set(finding.limitations + ["scoring_rules_not_configured"]))
    elif finding.score is not None and finding.score not in spec.score_values:
        raise ValueError("score_outside_skill_scale")
    if "time_calculator" in spec.required_tools:
        available = bool(time_facts) and all(
            f.get("tool_name") == "time_calculator"
            and f.get("status") == "completed"
            and f.get("data", {}).get("quality") == "confirmed"
            and f.get("data", {}).get("duration_seconds") is not None
            for f in time_facts
        )
        if finding.score is not None and not available:
            raise ValueError("required_time_facts_missing")
        if not available:
            finding.limitations = sorted(set(finding.limitations + ["required_time_facts_missing"]))
    finding.requires_manual_review = finding.requires_manual_review or bool(finding.review_rule_ids)


def validate_check(metric: dict, check: dict) -> dict:
    package = metric.get("skill")
    if not package:
        if check.get("review_rule_ids"):
            raise ValueError("review_rules_without_skill")
        return check
    spec = MetricSkillSpec.model_validate(package["spec"])
    rules = {rule.rule_id for rule in spec.manual_review}
    if not set(check.get("review_rule_ids", [])) <= rules:
        raise ValueError("unknown_verification_review_rule")
    if spec.status == "published" and (
        check.get("applicability_status") != "matched"
        or check.get("rubric_status") != "matched"
        or "review_rule_ids" not in check
    ):
        check.update(status="uncertain", reason="skill_applicability_or_rubric_not_verified")
    return check
