"""Regenerate the shareable JSON Schema from the Python contract."""

import json
from pathlib import Path

from app.skills.contracts import MetricSkillSpec


def main():
    output = Path(__file__).resolve().parents[1] / "docs/contracts/metric-skill-v1.schema.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(MetricSkillSpec.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
