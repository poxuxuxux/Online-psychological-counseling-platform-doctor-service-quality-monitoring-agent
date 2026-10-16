"""Three real, run-bound handlers. Identity, source text and timestamps are server-owned."""

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.communication import RunCommunicationPool
from app.domain.models import ConversationSession
from app.tools.dispatcher import ToolDispatcher
from app.tools.registry import ToolRegistry, ToolSpec


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeArguments(Arguments):
    metric_id: Literal["D2.1", "D2.2"]
    question_message_ids: list[str] = Field(default_factory=list, max_length=20)
    reply_message_id: str | None = None

    @model_validator(mode="after")
    def shape(self):
        if self.metric_id == "D2.1" and (
            self.question_message_ids or self.reply_message_id is not None
        ):
            raise ValueError("first_response_is_selected_by_tool")
        if self.metric_id == "D2.2" and (
            not self.question_message_ids
            or len(set(self.question_message_ids)) != len(self.question_message_ids)
        ):
            raise ValueError("question_ids_required_and_unique")
        return self


class HistoryArguments(Arguments):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=8, strict=True)


class QuoteRequest(Arguments):
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)
    start_offset: int | None = Field(default=None, ge=0, strict=True)


class EvidenceArguments(Arguments):
    items: list[QuoteRequest] = Field(min_length=1, max_length=40)


class HistoryRepository(Protocol):
    def for_patient(self, patient_ref: str) -> Sequence[ConversationSession]: ...


def aware(value: datetime | None) -> bool:
    return value is not None and value.tzinfo is not None and value.utcoffset() is not None


def terms(text: str) -> set[str]:
    found = set(re.findall(r"[a-z0-9]+", text.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        found.update(segment[i : i + 2] for i in range(len(segment) - 1))
    return found


class RunTools:
    def __init__(
        self,
        session: ConversationSession,
        pool: RunCommunicationPool,
        history_repository: HistoryRepository | None = None,
        history_authorized: bool = False,
    ):
        self.session = session.model_copy(deep=True)
        self.snapshot_id = (
            "snapshot-" + hashlib.sha256(self.session.model_dump_json().encode()).hexdigest()
        )
        self.pool = pool
        self.messages = {m.message_id: m for m in self.session.messages}
        if len(self.messages) != len(self.session.messages):
            raise ValueError("duplicate_message_ids")
        self.history_repository = history_repository
        self.history_authorized = history_authorized
        self.registry = ToolRegistry()
        self.registry.register(
            ToolSpec(
                "time_calculator",
                "Compute D2 intervals",
                frozenset({"process_response", "evidence_verification"}),
                TimeArguments,
            ),
            self._time,
        )
        self.registry.register(
            ToolSpec(
                "history_retrieval",
                "Retrieve authorized follow-up background",
                frozenset({"application", "manager"}),
                HistoryArguments,
            ),
            self._history,
        )
        self.registry.register(
            ToolSpec(
                "evidence_locator",
                "Bind current quotes",
                frozenset(
                    {
                        "professional_service",
                        "process_response",
                        "empathy_relationship",
                        "evidence_verification",
                        "risk_monitor",
                    }
                ),
                EvidenceArguments,
            ),
            self._evidence,
        )
        self.dispatcher = ToolDispatcher(self.registry)

    async def call(self, caller: str, name: str, arguments: dict) -> dict:
        call = self.pool.append(
            "tool_call",
            caller,
            {"tool_name": name, "arguments": arguments, "round_id": self.session.session_id},
        )
        try:
            result = await self.dispatcher.dispatch(caller, name, arguments)
        except PermissionError:
            result = {"status": "denied", "data": {}, "issues": ["tool_permission_denied"]}
        except (ValueError, KeyError):
            result = {"status": "failed", "data": {}, "issues": ["invalid_tool_arguments"]}
        except TimeoutError:
            result = {"status": "failed", "data": {}, "issues": ["tool_timeout"]}
        except Exception:  # noqa: BLE001 - tool boundary must not leak source or database errors
            result = {"status": "failed", "data": {}, "issues": ["tool_execution_failed"]}
        result = {
            **result,
            "tool_call_id": call["record_id"],
            "tool_name": name,
            "tool_version": "1.0.0",
            "source_snapshot_id": self.snapshot_id,
            "round_id": self.session.session_id,
        }
        self.pool.append("tool_result", caller, result, call["record_id"])
        return result

    async def _evidence(self, args: dict) -> dict:
        bindings, errors, issues = [], [], []
        for index, item in enumerate(args["items"]):
            message = self.messages.get(item["message_id"])
            code = None
            if message is None:
                code = "message_not_in_current_round"
            elif not item["quote"].strip():
                code = "empty_quote"
            else:
                quote = item["quote"]
                starts = []
                cursor = 0
                while True:
                    at = message.content.find(quote, cursor)
                    if at < 0:
                        break
                    starts.append(at)
                    cursor = at + 1
                offset = item.get("start_offset")
                if offset is not None:
                    starts = [offset] if offset in starts else []
                if not starts:
                    code = "quote_mismatch"
                elif len(starts) > 1:
                    code = "ambiguous_quote"
                else:
                    binding = {
                        "evidence_id": "evidence-" + str(uuid4()),
                        "round_id": self.session.session_id,
                        "message_id": message.message_id,
                        "display_sequence": message.sequence,
                        "role": message.role,
                        "timestamp": message.timestamp.isoformat()
                        if aware(message.timestamp)
                        else None,
                        "quote": message.content[starts[0] : starts[0] + len(quote)],
                        "source_ref": message.source_ref
                        or f"{self.session.session_id}/{message.message_id}",
                        "text_version": message.text_version,
                        "source_snapshot_id": self.snapshot_id,
                        "match_status": "matched",
                        "span": {
                            "start": starts[0],
                            "end": starts[0] + len(quote),
                            "unit": "unicode_code_point",
                        },
                    }
                    record = self.pool.append("evidence_binding", "evidence_locator", binding)
                    binding["pool_record_id"] = record["record_id"]
                    bindings.append(binding)
                    if not aware(message.timestamp):
                        issues.append("missing_or_unzoned_timestamp")
            if code:
                errors.append({"index": index, "message_id": item["message_id"], "code": code})
        return {
            "status": "partial" if errors or issues else "completed",
            "data": {"bindings": bindings, "item_issues": errors},
            "issues": sorted(set(issues)),
        }

    async def _time(self, args: dict) -> dict:
        metric = args["metric_id"]
        service = self.session.service_context
        data = {
            "metric_id": metric,
            "duration_seconds": None,
            "start": None,
            "end": None,
            "quality": "unavailable",
            "policy_version": "response-time-v1",
        }
        issues = []
        if service and service.state == "withdrawn":
            issues.append("withdrawn_order")
        if metric == "D2.1":
            if (
                service is None
                or not aware(service.consultation_started_at)
                or service.start_basis == "unknown"
            ):
                return {"status": "partial", "data": data, "issues": ["missing_order_start"]}
            start = service.consultation_started_at
            data.update(
                start={"ref": service.order_ref, "timestamp": start.isoformat()},
                basis=service.start_basis,
            )
            candidates = [
                m
                for m in self.session.messages
                if m.role == "doctor" and m.message_kind in ("dialogue", "unknown")
            ]
            if any(not aware(m.timestamp) for m in candidates):
                return {
                    "status": "partial",
                    "data": data,
                    "issues": ["ambiguous_first_reply_timestamp"],
                }
            candidates = sorted(
                (m for m in candidates if m.timestamp >= start),
                key=lambda m: (m.timestamp, m.sequence),
            )
            if not candidates:
                return {"status": "partial", "data": data, "issues": ["no_observed_reply"]}
            reply = candidates[0]
            if reply.message_kind == "unknown":
                return {"status": "partial", "data": data, "issues": ["ambiguous_first_reply_kind"]}
            quality = "confirmed" if service.start_basis == "order_timestamp" else "proxy"
        else:
            questions = [self.messages.get(mid) for mid in args["question_message_ids"]]
            if any(
                m is None or m.role != "patient" or m.message_kind != "dialogue" for m in questions
            ):
                return {"status": "partial", "data": data, "issues": ["invalid_question_reference"]}
            if any(not aware(m.timestamp) for m in questions):
                return {"status": "partial", "data": data, "issues": ["missing_question_timestamp"]}
            first = min(questions, key=lambda m: (m.timestamp, m.sequence))
            start = first.timestamp
            data.update(
                start={"message_id": first.message_id, "timestamp": start.isoformat()},
                question_message_ids=args["question_message_ids"],
                basis="agent_proposed_pair",
            )
            reply = self.messages.get(args["reply_message_id"])
            if reply is None:
                return {"status": "partial", "data": data, "issues": ["no_matched_reply"]}
            if (
                reply.role != "doctor"
                or reply.message_kind != "dialogue"
                or not aware(reply.timestamp)
            ):
                return {"status": "partial", "data": data, "issues": ["invalid_reply_reference"]}
            if reply.timestamp < max(m.timestamp for m in questions):
                return {"status": "partial", "data": data, "issues": ["reply_before_question"]}
            quality = "confirmed"
        data.update(
            end={"message_id": reply.message_id, "timestamp": reply.timestamp.isoformat()},
            duration_seconds=(reply.timestamp - start).total_seconds(),
            quality=quality,
        )
        return {
            "status": "partial" if issues or quality == "proxy" else "completed",
            "data": data,
            "issues": issues,
        }

    async def _history(self, args: dict) -> dict:
        empty = {"fragments": [], "retrieval_version": "history-overlap-v1", "truncated": False}
        if self.session.consultation_round != "follow_up":
            return {
                "status": "skipped",
                "data": empty,
                "issues": [
                    "not_follow_up"
                    if self.session.consultation_round == "initial"
                    else "visit_type_unknown"
                ],
            }
        patient = self.session.anonymized_patient_ref
        if not patient:
            return {"status": "skipped", "data": empty, "issues": ["patient_link_unavailable"]}
        if not self.history_authorized:
            return {"status": "denied", "data": empty, "issues": ["history_not_authorized"]}
        service = self.session.service_context
        if not service or not aware(service.consultation_started_at):
            return {"status": "skipped", "data": empty, "issues": ["history_cutoff_unavailable"]}
        if self.history_repository is None:
            return {"status": "failed", "data": empty, "issues": ["history_repository_unavailable"]}
        cutoff = service.consultation_started_at
        query_terms = terms(args["query"])
        if not query_terms:
            return {"status": "failed", "data": empty, "issues": ["empty_history_query"]}
        ranked = []
        for old in self.history_repository.for_patient(patient):
            if (
                old.session_id == self.session.session_id
                or old.anonymized_patient_ref != patient
                or old.source_id != self.session.source_id
            ):
                continue
            valid = [
                m
                for m in old.messages
                if aware(m.timestamp)
                and m.timestamp < cutoff
                and m.content.strip()
                and (
                    (m.role in ("patient", "doctor") and m.message_kind == "dialogue")
                    or m.patient_submitted_intake
                )
                and (m.modality == "text" or m.transcript is not None)
            ]
            for message in valid:
                overlap = query_terms & terms(message.content)
                if overlap:
                    ranked.append((len(overlap), old, message))
        ranked.sort(
            key=lambda row: (row[0], row[2].timestamp.astimezone(UTC), row[2].message_id),
            reverse=True,
        )
        fragments = []
        budget = 6000
        for _, old, message in ranked[: args["top_k"]]:
            if len(message.content) > budget:
                empty["truncated"] = True
                continue
            budget -= len(message.content)
            fragments.append(
                {
                    "fragment_id": "history-" + str(uuid4()),
                    "round_id": old.session_id,
                    "source_ref": message.source_ref
                    or f"{old.source_id}/{old.session_id}/{message.message_id}",
                    "consultation_date": message.timestamp.date().isoformat(),
                    "messages": [
                        {
                            "message_id": message.message_id,
                            "role": message.role,
                            "timestamp": message.timestamp.isoformat(),
                            "text": message.content,
                        }
                    ],
                    "match_reason": "query_term_overlap",
                    "usage": "background_only",
                }
            )
        empty.update(
            fragments=fragments, truncated=empty["truncated"] or len(ranked) > len(fragments)
        )
        return {"status": "completed", "data": empty, "issues": []}
