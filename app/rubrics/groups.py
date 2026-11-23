# 环节：团队分组配置层；用途：把原始评价维度映射为主责 Agent 的可调整职责组。
"""Evaluation dimension groupings used to assign rubric metrics to evaluator agents."""

TEAM_DIMENSION_GROUPS = (
    {"group_id": "D1+D3", "lead_dimension": "D1", "dimension_ids": ("D1", "D3")},
    {"group_id": "D2+D5", "lead_dimension": "D2", "dimension_ids": ("D2", "D5")},
    {"group_id": "D4+D6", "lead_dimension": "D4", "dimension_ids": ("D4", "D6")},
)


def evaluator_groups(metrics):
    """Return configured groups plus singleton groups for any future/unmapped dimensions."""
    dimensions = {spec["dimension_id"] for spec in metrics.values()}
    groups = [
        {**group, "dimension_ids": [d for d in group["dimension_ids"] if d in dimensions]}
        for group in TEAM_DIMENSION_GROUPS
    ]
    groups = [group for group in groups if group["dimension_ids"]]
    assigned = {dimension for group in groups for dimension in group["dimension_ids"]}
    groups.extend(
        {"group_id": dimension, "lead_dimension": dimension, "dimension_ids": [dimension]}
        for dimension in sorted(dimensions - assigned)
    )
    return groups
