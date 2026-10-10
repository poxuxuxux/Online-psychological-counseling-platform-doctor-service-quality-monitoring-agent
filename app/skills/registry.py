"""功能：扫描 Skill 包并读取元数据；指标规则保存在 Skill 文件而非代码分支中。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillMetadata:
    """Skill 可检索目录项；完整评价指引由 loader 按需读取。"""

    skill_id: str
    name: str
    version: str
    description: str
    directory: Path


class SkillRegistry:
    """在指定目录发现并校验 Skill 元数据，避免系统提示词加载全部全文。"""

    def __init__(self, packages_dir: Path) -> None:
        self._packages_dir = packages_dir
        self._skills: dict[str, SkillMetadata] = {}

    def scan(self) -> dict[str, SkillMetadata]:
        """扫描子目录中的 metric.yaml；重复 ID 或字段缺失会立即报错。"""
        discovered: dict[str, SkillMetadata] = {}
        for metadata_path in self._packages_dir.glob("*/metric.yaml"):
            data: dict[str, Any] = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
            skill = SkillMetadata(
                skill_id=str(data["id"]),
                name=str(data["name"]),
                version=str(data["version"]),
                description=str(data["description"]),
                directory=metadata_path.parent,
            )
            if skill.skill_id in discovered:
                raise ValueError(f"Duplicate skill ID: {skill.skill_id}")
            if not (skill.directory / "SKILL.md").is_file():
                raise ValueError(f"Skill instructions missing for: {skill.skill_id}")
            discovered[skill.skill_id] = skill
        self._skills = discovered
        return dict(self._skills)

    def get(self, skill_id: str) -> SkillMetadata:
        """返回已发现 Skill 元数据；不会因为请求自动加载任意路径。"""
        try:
            return self._skills[skill_id]
        except KeyError as error:
            raise KeyError(f"Skill is not registered: {skill_id}") from error
