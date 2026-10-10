"""功能：定义会话评价用例入口；稍后接入路由、上下文构建、核验和报告。"""

from app.domain.models import ConversationSession, EvaluationReport


class EvaluateSessionUseCase:
    """封装单次会话评价的应用流程，避免将业务编排写进 FastAPI 路由。"""

    async def execute(self, session: ConversationSession) -> EvaluationReport:
        """占位接口：完整流程接通前显式报错，避免返回伪造评价结果。"""
        raise NotImplementedError(
            f"Evaluation pipeline is not wired yet for session {session.session_id}"
        )
