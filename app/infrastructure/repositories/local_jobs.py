"""Single-worker local SQLite development store. Not a Railway/PostgreSQL replacement."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class LocalJobStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rounds(
                    id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, round_id TEXT NOT NULL, idem TEXT UNIQUE NOT NULL,
                    snapshot TEXT NOT NULL, rubric TEXT NOT NULL,
                    status TEXT NOT NULL, report TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    stage TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS communication_records(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE NOT NULL, run_id TEXT NOT NULL REFERENCES jobs(id),
                    record_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS communication_run_seq ON communication_records(run_id,seq);
                CREATE TRIGGER IF NOT EXISTS communication_no_update
                    BEFORE UPDATE ON communication_records BEGIN
                    SELECT RAISE(ABORT,'communication_records_are_append_only'); END;
                CREATE TRIGGER IF NOT EXISTS communication_no_delete
                    BEFORE DELETE ON communication_records BEGIN
                    SELECT RAISE(ABORT,'communication_records_are_append_only'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_round(self, round_id: str, source_kind: str, data: dict):
        encoded = json.dumps(data, ensure_ascii=False)
        with self.connect() as db:
            old = db.execute(
                "SELECT source_kind,data FROM rounds WHERE id=?", (round_id,)
            ).fetchone()
            if old and (old["source_kind"] != source_kind or old["data"] != encoded):
                raise ValueError("round_snapshot_conflict")
            db.execute(
                "INSERT OR IGNORE INTO rounds VALUES (?,?,?)", (round_id, source_kind, encoded)
            )

    def list_rounds(self, limit: int, offset: int):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,source_kind FROM rounds ORDER BY id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            ]

    def round(self, round_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
            if row is None:
                raise KeyError("round_not_found")
            return {
                "id": row["id"],
                "source_kind": row["source_kind"],
                "data": json.loads(row["data"]),
            }

    def for_patient(self, patient_ref: str):
        """Filter trusted synthetic source rows by patient BEFORE relevance ranking; never read reports."""
        from app.domain.models import ConversationSession

        with self.connect() as db:
            rows = db.execute(
                "SELECT data FROM rounds WHERE source_kind='server_synthetic' "
                "AND json_extract(data,'$.anonymized_patient_ref')=?",
                (patient_ref,),
            ).fetchall()
        return [ConversationSession.model_validate_json(row["data"]) for row in rows]

    def enqueue(self, round_id: str, idem: str, rubric: dict):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM jobs WHERE idem=?", (idem,)).fetchone()
            encoded_rubric = json.dumps(rubric, ensure_ascii=False)
            if existing:
                if existing["round_id"] != round_id or existing["rubric"] != encoded_rubric:
                    raise ValueError("idempotency_conflict")
                return existing["id"]
            source = db.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
            if source is None:
                raise KeyError("round_not_found")
            if source["source_kind"] != "server_synthetic":
                raise ValueError("real_data_evaluation_not_enabled")
            job_id = "run-" + str(uuid.uuid4())
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,NULL,NULL)",
                (job_id, round_id, idem, source["data"], encoded_rubric, "queued"),
            )
            db.execute(
                "INSERT INTO events(job_id,stage,data) VALUES (?,?,?)", (job_id, "queued", "{}")
            )
            return job_id

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
            return dict(row)

    def event(self, job_id: str, stage: str, data: dict):
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(job_id,stage,data) VALUES (?,?,?)",
                (job_id, stage, json.dumps(data, ensure_ascii=False)),
            )

    def append_pool_record(self, record: dict):
        from app.application.communication import PoolRecord

        checked = PoolRecord.model_validate(record)
        with self.connect() as db:
            for ref in (checked.correlation_id, checked.supersedes_record_id):
                if (
                    ref is not None
                    and db.execute(
                        "SELECT 1 FROM communication_records WHERE record_id=? AND run_id=?",
                        (ref, checked.run_id),
                    ).fetchone()
                    is None
                ):
                    raise ValueError("cross_run_or_missing_pool_reference")
            db.execute(
                "INSERT INTO communication_records(record_id,run_id,record_json) VALUES (?,?,?)",
                (checked.record_id, checked.run_id, checked.model_dump_json()),
            )

    def pool_records(
        self, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[dict]:
        with self.connect() as db:
            return [
                dict(json.loads(row["record_json"]), sequence=row["seq"])
                for row in db.execute(
                    "SELECT seq,record_json FROM communication_records WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                    (run_id, after_sequence, limit if limit is not None else -1),
                )
            ]

    def finish(self, job_id: str, report: dict | None, error: str | None = None):
        with self.connect() as db:
            status = report["status"] if report else "failed"
            changed = db.execute(
                "UPDATE jobs SET status=?,report=?,error=? WHERE id=? AND status='running'",
                (status, json.dumps(report, ensure_ascii=False) if report else None, error, job_id),
            ).rowcount
            if changed != 1:
                raise ValueError("invalid_job_transition")
            db.execute(
                "INSERT INTO events(job_id,stage,data) VALUES (?,?,?)", (job_id, status, "{}")
            )

    def interrupt(self, job_id: str):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status='interrupted',error='worker_interrupted' "
                "WHERE id=? AND status='running'",
                (job_id,),
            )

    def recover_interrupted(self):
        # Explicit CLI recovery, only while the worker is stopped. Never silently replay paid calls.
        with self.connect() as db:
            return db.execute(
                "UPDATE jobs SET status='interrupted',error='worker_interrupted' "
                "WHERE status='running'"
            ).rowcount

    def job(self, job_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT id,round_id,status,report,error FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("job_not_found")
            result = dict(row)
            result["report"] = json.loads(result["report"]) if result["report"] else None
            result["events"] = [
                dict(e)
                for e in db.execute(
                    "SELECT seq,stage,created_at FROM events WHERE job_id=? ORDER BY seq", (job_id,)
                )
            ]
            return result
