"""Load declarative metric packages into a frozen, content-addressed rule snapshot."""

import hashlib
import json
from pathlib import Path

import yaml

from app.skills.contracts import MetricSkillSpec


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError("Duplicate YAML key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_metric_package(directory: Path) -> dict:
    root = directory.resolve()
    contents = {}
    for name in ("metric.yaml", "SKILL.md"):
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise ValueError("Skill file must stay inside its package")
        if path.stat().st_size > 256_000:
            raise ValueError("Skill file exceeds 256 KB")
        contents[name] = path.read_text(encoding="utf-8-sig")
    spec = MetricSkillSpec.model_validate(
        yaml.load(contents["metric.yaml"], Loader=UniqueKeyLoader)
    )
    if not contents["SKILL.md"].strip():
        raise ValueError("Skill instructions must not be empty")
    payload = {"spec": spec.model_dump(mode="json"), "instructions": contents["SKILL.md"]}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return {**payload, "content_hash": digest}


def merge_metric_packages(base: dict, packages_dir: Path) -> dict:
    """Unprovided metrics stay unconfigured; invalid supplied packages fail explicitly."""
    result = json.loads(json.dumps(base))
    metrics = {metric["metric_id"]: metric for metric in result["metrics"]}
    seen = set()
    for manifest in sorted(packages_dir.glob("*/metric.yaml")):
        if not manifest.parent.resolve().is_relative_to(packages_dir.resolve()):
            raise ValueError("Skill package must stay inside configured root")
        package = load_metric_package(manifest.parent)
        spec = package["spec"]
        mid = spec["metric_id"]
        if mid not in metrics or mid in seen:
            raise ValueError("Unknown or duplicate metric Skill")
        if spec["owner"] != metrics[mid]["owner"]:
            raise ValueError("Skill owner conflicts with canonical routing")
        seen.add(mid)
        metrics[mid].update(
            name=spec["name"],
            definition=spec["definition"],
            skill=package,
            scoring_status="configured" if spec["status"] == "published" else "not_configured",
        )
    if seen:
        digest = hashlib.sha256(
            json.dumps(result["metrics"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        result["version"] = base["version"] + "+" + digest[:16]
        result["status"] = (
            "published"
            if all(m["scoring_status"] == "configured" for m in result["metrics"])
            else "partial"
        )
    return result
