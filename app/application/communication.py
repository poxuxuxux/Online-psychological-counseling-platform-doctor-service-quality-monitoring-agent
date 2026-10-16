"""Run-scoped, append-only communication pool; agents receive only scoped records."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class PoolRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(default_factory=lambda: "record-" + str(uuid4()))
    run_id: str
    kind: Literal[
        "context",
        "task",
        "task_status",
        "finding",
        "verification",
        "conflict",
        "arbitration",
        "revision",
        "adoption",
        "summary",
        "failure",
        "tool_call",
        "tool_result",
        "evidence_binding",
        "hook_run",
        "hook_result",
        "risk_signal",
        "conflict_detection",
    ]
    source: str
    payload: dict
    correlation_id: str | None = None
    supersedes_record_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: str = "1.0"


class PoolStorage(Protocol):
    def append_pool_record(self, record: dict) -> None: ...
    def pool_records(self, run_id: str) -> list[dict]: ...


class RunCommunicationPool:
    def __init__(self, run_id: str, storage: PoolStorage | None = None):
        self.run_id = run_id
        self._storage = storage
        self._records: list[dict] = []

    def append(
        self,
        kind: str,
        source: str,
        payload: dict,
        correlation_id: str | None = None,
        supersedes_record_id: str | None = None,
    ) -> dict:
        if correlation_id is not None:
            self.get(correlation_id)
        if supersedes_record_id is not None:
            self.get(supersedes_record_id)
        record = PoolRecord(
            run_id=self.run_id,
            kind=kind,
            source=source,
            payload=deepcopy(payload),
            correlation_id=correlation_id,
            supersedes_record_id=supersedes_record_id,
        )
        data = record.model_dump(mode="json")
        if self._storage is None:
            self._records.append(data)
        else:
            self._storage.append_pool_record(data)
        return deepcopy(data)

    def read(self, kind: str | None = None) -> list[dict]:
        records = self._storage.pool_records(self.run_id) if self._storage else self._records
        return deepcopy([r for r in records if kind is None or r["kind"] == kind])

    def get(self, record_id: str) -> dict:
        for record in self.read():
            if record["record_id"] == record_id:
                return record
        raise KeyError("record_not_in_current_run")
