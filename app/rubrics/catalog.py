# 环节：指标目录层；用途：加载、校验并组织 Agent 评价规则。
"""Load existing metric.yaml + SKILL.md packages; discover dimensions from data."""

import hashlib
import json
import re
from pathlib import Path

import yaml

from app.rubrics.payload import metric_payload


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in values:
            raise ValueError(f"Duplicate YAML key: {key}")
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


class SkillCatalog:
    def __init__(self, root: Path):
        self.metrics = {}
        for path in sorted(root.glob("*/metric.yaml")):
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Skill outside configured directory")
            spec = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueLoader)
            instructions = path.with_name("SKILL.md").read_text(encoding="utf-8-sig")
            mid = spec["metric_id"]
            if mid in self.metrics or not re.fullmatch(r"[A-Za-z][\w-]*\.[\w-]+", mid):
                raise ValueError(f"Invalid/duplicate metric ID: {mid}")
            scores = spec["score_values"]
            if not scores or any(type(s) is not int or not 0 <= s <= 5 for s in scores):
                raise ValueError(f"Invalid score values: {mid}")
            anchors = [a["score"] for a in spec["anchors"]]
            if len(set(anchors)) != len(anchors) or set(anchors) != set(scores):
                raise ValueError(f"Incomplete score anchors: {mid}")
            if spec.get("status") not in {"draft", "published"}:
                raise ValueError(f"Invalid publication status: {mid}")
            rules = [r["rule_id"] for r in spec["manual_review"]]
            if len(set(rules)) != len(rules):
                raise ValueError(f"Duplicate review rules: {mid}")
            issues = []
            if spec["status"] == "published" and re.search(r"status\s*[:=]\s*draft", instructions):
                issues.append("skill_publication_conflict")
            self.metrics[mid] = {
                **spec,
                "dimension_id": spec.get("dimension_id", mid.split(".")[0]),
                "instructions": instructions,
                "configuration_issues": issues,
                "weight": float(spec.get("weight", 1)),
            }
            if self.metrics[mid]["weight"] <= 0:
                raise ValueError("Metric weights must be positive")
        if not self.metrics:
            raise ValueError("No metric packages found")
        self.version = (
            "skills-"
            + hashlib.sha256(
                json.dumps(self.metrics, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()[:16]
        )

    @property
    def dimensions(self):
        return sorted({m["dimension_id"] for m in self.metrics.values()})

    def snapshot(self):
        return {"version": self.version, "metrics": self.metrics}


class SkillKnowledgeSource:
    """Local, versioned knowledge; no invented external clinical references."""

    def __init__(self, catalog: SkillCatalog):
        self.catalog = catalog

    async def search(self, query: str, metric_ids: list[str]) -> list[dict]:
        return [
            {
                "source_id": mid,
                "version": m["version"],
                "title": m["name"],
                "text": json.dumps(metric_payload(m), ensure_ascii=False),
            }
            for mid, m in self.catalog.metrics.items()
            if (not metric_ids or mid in metric_ids)
            and (not query or query.casefold() in (m["name"] + m["instructions"]).casefold())
        ][:5]
