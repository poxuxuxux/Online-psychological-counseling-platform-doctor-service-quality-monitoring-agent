"""功能：组合根；集中装配预处理管道、注册表、仓储和评价编排组件。"""

from dataclasses import dataclass
from pathlib import Path

from app.agents.registry import AgentRegistry
from app.application.context.builder import ContextBuilder
from app.application.hooks.registry import HookRegistry
from app.application.orchestration.coordinator import EvaluationBudget, EvaluationCoordinator
from app.application.orchestration.router import PolicyRouter
from app.application.preprocessing.pipeline import PreprocessingPipeline
from app.application.preprocessing.stages import (
    DesensitizationStage,
    NormalizationStage,
    PreflightStage,
    TranscriptionStage,
)
from app.application.use_cases.evaluate_session import EvaluateSessionUseCase
from app.core.config import Settings, get_settings
from app.evaluation.evidence_verifier import EvidenceVerifier
from app.evaluation.report_builder import ReportBuilder
from app.infrastructure.media.storage import LocalMediaStorage
from app.infrastructure.media.transcriber import UnconfiguredTranscriber
from app.infrastructure.repositories.ledger import InMemorySharedLedger
from app.infrastructure.repositories.sessions import InMemorySessionRepository
from app.infrastructure.security.redactor import (
    InMemoryRedactionMapRepository,
    SyntheticDemoRedactor,
)
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class RuntimeContainer:
    """应用运行时组件集合；API 与用例都从这里取依赖，不自行构造。"""

    settings: Settings
    session_repository: InMemorySessionRepository
    redaction_map_repository: InMemoryRedactionMapRepository
    media_storage: LocalMediaStorage
    shared_ledger: InMemorySharedLedger
    agent_registry: AgentRegistry
    tool_registry: ToolRegistry
    hook_registry: HookRegistry
    pipeline: PreprocessingPipeline
    router: PolicyRouter
    context_builder: ContextBuilder
    coordinator: EvaluationCoordinator
    evaluate_session: EvaluateSessionUseCase


def build_container(settings: Settings | None = None) -> RuntimeContainer:
    """装配全部组件；合成数据脱敏器在接入真实数据前必须替换。"""
    settings = settings or get_settings()
    redaction_map_repository = InMemoryRedactionMapRepository()
    media_storage = LocalMediaStorage(Path(settings.media_storage_dir))

    pipeline = PreprocessingPipeline(
        stages=(
            NormalizationStage(),
            TranscriptionStage(
                transcriber=UnconfiguredTranscriber(),
                min_confidence=settings.min_transcript_confidence,
            ),
            # 仅限合成演示数据：接入真实/授权数据前必须换成审定的规则脱敏器。
            DesensitizationStage(
                redactor=SyntheticDemoRedactor(),
                map_repository=redaction_map_repository,
            ),
            PreflightStage(max_unknown_role_ratio=settings.max_unknown_role_ratio),
        )
    )
    agent_registry = AgentRegistry()
    router = PolicyRouter()
    context_builder = ContextBuilder()
    shared_ledger = InMemorySharedLedger()
    coordinator = EvaluationCoordinator(
        registry=agent_registry,
        budget=EvaluationBudget(
            agent_timeout_seconds=settings.agent_timeout_seconds,
            max_concurrency=settings.max_agent_concurrency,
        ),
        ledger=shared_ledger,
    )
    return RuntimeContainer(
        settings=settings,
        session_repository=InMemorySessionRepository(),
        redaction_map_repository=redaction_map_repository,
        media_storage=media_storage,
        shared_ledger=shared_ledger,
        agent_registry=agent_registry,
        tool_registry=ToolRegistry(),
        hook_registry=HookRegistry(),
        pipeline=pipeline,
        router=router,
        context_builder=context_builder,
        coordinator=coordinator,
        evaluate_session=EvaluateSessionUseCase(
            pipeline=pipeline,
            router=router,
            context_builder=context_builder,
            coordinator=coordinator,
            evidence_verifier=EvidenceVerifier(),
            report_builder=ReportBuilder(),
        ),
    )
