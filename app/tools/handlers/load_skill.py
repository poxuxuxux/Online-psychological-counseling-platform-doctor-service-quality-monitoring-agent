"""功能：把已注册 Skill 的按需加载能力包装为可注册的只读工具 Handler。"""

from typing import Any

from app.skills.loader import SkillLoader


def create_load_skill_handler(loader: SkillLoader):
    """创建闭包 Handler；模型传入 Skill ID，加载器只读取已注册的 Skill。"""

    async def handle(arguments: dict[str, Any]) -> dict[str, str]:
        """返回 Skill 正文；真实注册时须限制每个 Agent 可加载的 Skill ID。"""
        skill_id = str(arguments["skill_id"])
        return {"skill_id": skill_id, "instructions": loader.load(skill_id)}

    return handle
