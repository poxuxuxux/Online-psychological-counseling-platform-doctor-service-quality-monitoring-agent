# 环节：会话上下文层；用途：负责对话预处理、初复诊路由及历史上下文构建。
from datetime import UTC, datetime

from app.domain.models import Session


def preprocess(session: Session) -> dict:
    data = session.model_dump(mode="json")
    data["messages"].sort(key=lambda m: m["sequence"])
    # Convert before DB ordering; lexicographic ISO timestamps then have consistent UTC semantics.
    for key in ("session_time", "imported_at"):
        if data[key]:
            data[key] = datetime.fromisoformat(data[key]).astimezone(UTC).isoformat()
    for m in data["messages"]:
        if m["timestamp"]:
            m["timestamp"] = datetime.fromisoformat(m["timestamp"]).astimezone(UTC).isoformat()
    data["consultation_round"] = "unknown"  # Never trust a caller's guessed visit label.
    return data


class SessionContextManager:
    def __init__(self, repository):
        self.repository = repository

    async def route(self, session):
        identifiable = all(session.get(k) for k in ("patient_id", "doctor_id", "session_time"))
        history = await self.repository.history(session) if identifiable else []
        kind = (
            "FOLLOW_UP"
            if history
            else "INITIAL"
            if identifiable and session["history_complete"]
            else "UNKNOWN"
        )
        return {
            "session_type": kind,
            "history": history,
            "history_status": "available"
            if history
            else "complete_empty"
            if kind == "INITIAL"
            else "incomplete",
            "history_limit": 20,
        }


def build_history_context(context):
    history = context["history"]
    reports = [h["report"] for h in history if h.get("report")]
    return {
        **context,
        "previous_session_count": len(history),
        "latest_evaluation": reports[0] if reports else None,
        "historical_risks": [
            {"session_id": h["session"]["session_id"], "risk": h["report"].get("risk")}
            for h in history
            if h.get("report") and h["report"].get("risk")
        ],
        "follow_up_focus": list(
            dict.fromkeys(reason for r in reports for reason in r.get("review_reasons", []))
        )[:20],
    }


def evaluator_context(context):
    """Only routing metadata in routine evaluation; no past scores, ranks or summaries."""
    return {
        k: context[k]
        for k in ("session_type", "history_status", "previous_session_count")
        if k in context
    }
