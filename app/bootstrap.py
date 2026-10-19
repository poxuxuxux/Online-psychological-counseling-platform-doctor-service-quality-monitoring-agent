# 环节：依赖装配层；用途：创建并注入模型、仓储、规则目录与工作流服务。
from dataclasses import dataclass

from app.config import Settings
from app.context.service import preprocess
from app.demo import sessions
from app.infrastructure.model import JsonModelGateway
from app.infrastructure.repository import Repository
from app.rubrics.catalog import SkillCatalog, SkillKnowledgeSource
from app.workflow.service import EvaluationService


@dataclass
class Container:
    settings: Settings
    repository: Repository
    service: EvaluationService
    catalog: SkillCatalog
    model: object


async def build_container(settings=None, repository=None, model=None, catalog=None):
    settings = settings or Settings.from_env()
    repository = repository or Repository(settings.database_url)
    model = model or JsonModelGateway()
    catalog = catalog or SkillCatalog(settings.skill_dir)
    await repository.initialize()
    if settings.seed_demo:
        for session in sessions():
            await repository.save_session(preprocess(session))
    service = EvaluationService(settings, repository, model, catalog, SkillKnowledgeSource(catalog))
    return Container(settings, repository, service, catalog, model)
