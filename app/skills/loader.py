"""功能：按需读取已注册 Skill 的 Markdown 指引，不把 Skill 当可执行代码。"""

from app.skills.registry import SkillRegistry


class SkillLoader:
    """只加载 Registry 已发现的 Skill，隔离用户输入与文件系统路径。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def load(self, skill_id: str) -> str:
        """读取某个 Skill 的评价说明；找不到 Skill 时明确报错。"""
        metadata = self._registry.get(skill_id)
        return (metadata.directory / "SKILL.md").read_text(encoding="utf-8")
