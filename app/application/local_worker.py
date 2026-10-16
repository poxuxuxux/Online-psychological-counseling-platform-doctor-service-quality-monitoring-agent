"""Explicit local worker; paid model execution is separate from HTTP submission."""

import asyncio
import json

from app.agents.structured import StructuredEvaluation
from app.application.communication import RunCommunicationPool
from app.domain.models import ConversationSession
from app.infrastructure.repositories.local_jobs import LocalJobStore


async def run_one(store: LocalJobStore, engine: StructuredEvaluation) -> bool:
    job = store.claim()
    if job is None:
        return False
    try:
        session = ConversationSession.model_validate_json(job["snapshot"])
        engine = StructuredEvaluation(
            engine.provider,
            rubric=json.loads(job["rubric"]),
            history_repository=store,
            history_authorized=session.source_id == "synthetic-demo",
        )
        report = await asyncio.wait_for(
            engine.run(
                session,
                lambda stage, data: store.event(job["id"], stage, data),
                pool=RunCommunicationPool(job["id"], store),
            ),
            timeout=600,
        )
        report["evaluation_id"] = job["id"]
        store.finish(job["id"], report)
    except asyncio.CancelledError:
        store.interrupt(job["id"])
        raise
    except Exception:  # noqa: BLE001 - durable job boundary; never persist raw provider exceptions
        store.finish(job["id"], None, "evaluation_failed")
    return True
