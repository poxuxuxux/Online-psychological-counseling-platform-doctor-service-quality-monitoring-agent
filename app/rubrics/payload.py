# 环节：指标目录层；用途：加载、校验并组织 Agent 评价规则。
"""Model-facing rule projection parsed from SKILL.md frontmatter and body."""


def metric_payload(spec):
    result = {
        key: value
        for key, value in spec.items()
        if key not in {"configuration_issues", "owner", "weight", "schema_version"}
    }
    if spec["status"] == "published":
        result["manual_review"] = [
            r for r in result["manual_review"] if r["rule_id"] != "rubric_unpublished"
        ]
    return result


def task_payload(task):
    result = {
        key: value
        for key, value in task.items()
        if key
        not in {"created_at", "updated_at", "evaluation_run_id", "revisions", "model_seconds"}
    }
    # The frozen rule projection is already present once in the request.
    result["observations"] = [
        {"tool": "read_skill", "result": {"loaded": True}} if item["tool"] == "read_skill" else item
        for item in task["observations"]
    ]
    return result
