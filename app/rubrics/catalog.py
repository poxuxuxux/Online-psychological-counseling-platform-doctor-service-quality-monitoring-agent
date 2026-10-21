# 环节：指标目录层；用途：加载、校验并组织 Agent 评价规则。
"""Load each metric's structured frontmatter and instructions from SKILL.md."""

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
        for path in sorted(root.glob("*/SKILL.md")):
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Skill outside configured directory")
            source = path.read_text(encoding="utf-8-sig")
            match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", source, re.DOTALL)
            if not match:
                raise ValueError(f"Missing SKILL.md YAML frontmatter: {path}")
            spec = yaml.load(match.group(1), Loader=UniqueLoader)
            if not isinstance(spec, dict):
                raise TypeError(f"Invalid SKILL.md YAML frontmatter: {path}")
            instructions = match.group(2)
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
            if spec.get("time_fact") not in {None, "first_response_seconds", "adjacent_response_intervals"}:
                raise ValueError(f"Invalid required time fact: {mid}")
            if spec.get("time_fact") and "time_calculator" not in spec.get("required_tools", []):
                raise ValueError(f"Time fact requires time_calculator: {mid}")
            rules = [r["rule_id"] for r in spec["manual_review"]]
            if len(set(rules)) != len(rules):
                raise ValueError(f"Duplicate review rules: {mid}")
            issues = []
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
