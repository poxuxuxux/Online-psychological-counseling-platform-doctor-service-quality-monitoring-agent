"""PostgreSQL storage for the metric evaluation API and its separate worker."""

import json
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostgresJobStore:
    def __init__(self, database_url: str):
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("Metric jobs require a PostgreSQL DATABASE_URL")
        self.database_url = database_url
        self.initialize()

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize(self):
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS metric_rounds (
                    id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, data JSONB NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS metric_jobs (
                    id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES metric_rounds(id),
                    idem TEXT UNIQUE NOT NULL, snapshot JSONB NOT NULL, rubric JSONB NOT NULL,
                    status TEXT NOT NULL, report JSONB, error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS metric_job_events (
                    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES metric_jobs(id), stage TEXT NOT NULL,
                    data JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS metric_communication_records (
                    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    record_id TEXT UNIQUE NOT NULL,
                    run_id TEXT NOT NULL REFERENCES metric_jobs(id),
                    record_json JSONB NOT NULL
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS metric_communication_run_seq
                ON metric_communication_records(run_id, seq)
            """)

    def save_round(self, round_id: str, source_kind: str, data: dict):
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (round_id,))
            old = db.execute(
                "SELECT source_kind, data FROM metric_rounds WHERE id=%s FOR UPDATE", (round_id,)
            ).fetchone()
            if old and (old["source_kind"] != source_kind or old["data"] != data):
                raise ValueError("round_snapshot_conflict")
            db.execute(
                "INSERT INTO metric_rounds(id, source_kind, data) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (round_id, source_kind, Jsonb(data)),
            )

    def round(self, round_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT id, source_kind, data FROM metric_rounds WHERE id=%s", (round_id,)
            ).fetchone()
        if row is None:
            raise KeyError("round_not_found")
        return row

    def list_rounds(self, limit: int, offset: int):
        with self.connect() as db:
            return db.execute(
                "SELECT id, source_kind FROM metric_rounds ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()

    def for_patient(self, patient_ref: str):
        from app.domain.models import ConversationSession

        with self.connect() as db:
            rows = db.execute(
                "SELECT data FROM metric_rounds WHERE source_kind='server_synthetic' "
                "AND data->>'anonymized_patient_ref'=%s",
                (patient_ref,),
            ).fetchall()
        return [ConversationSession.model_validate(row["data"]) for row in rows]

    def enqueue(self, round_id: str, idem: str, rubric: dict):
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (idem,))
            existing = db.execute(
                "SELECT id, round_id, rubric FROM metric_jobs WHERE idem=%s FOR UPDATE", (idem,)
            ).fetchone()
            if existing:
                if existing["round_id"] != round_id or existing["rubric"] != rubric:
                    raise ValueError("idempotency_conflict")
                return existing["id"]
            source = db.execute(
                "SELECT source_kind, data FROM metric_rounds WHERE id=%s", (round_id,)
            ).fetchone()
            if source is None:
                raise KeyError("round_not_found")
            if source["source_kind"] != "server_synthetic":
                raise ValueError("real_data_evaluation_not_enabled")
            job_id = "run-" + str(uuid.uuid4())
            db.execute(
                "INSERT INTO metric_jobs(id,round_id,idem,snapshot,rubric,status) "
                "VALUES (%s,%s,%s,%s,%s,'queued')",
                (job_id, round_id, idem, Jsonb(source["data"]), Jsonb(rubric)),
            )
            db.execute(
                "INSERT INTO metric_job_events(job_id,stage,data) VALUES (%s,'queued',%s)",
                (job_id, Jsonb({})),
            )
            return job_id

    def claim(self):
        with self.connect() as db:
            row = db.execute("""
                SELECT id, snapshot, rubric FROM metric_jobs WHERE status='queued'
                ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
            """).fetchone()
            if row is None:
                return None
            db.execute("UPDATE metric_jobs SET status='running' WHERE id=%s", (row["id"],))
            return {
                "id": row["id"],
                "snapshot": json.dumps(row["snapshot"], ensure_ascii=False),
                "rubric": json.dumps(row["rubric"], ensure_ascii=False),
            }

    def event(self, job_id: str, stage: str, data: dict):
        with self.connect() as db:
            db.execute(
                "INSERT INTO metric_job_events(job_id,stage,data) VALUES (%s,%s,%s)",
                (job_id, stage, Jsonb(data)),
            )

    def append_pool_record(self, record: dict):
        from app.application.communication import PoolRecord

        checked = PoolRecord.model_validate(record)
        with self.connect() as db:
            for ref in (checked.correlation_id, checked.supersedes_record_id):
                if ref and not db.execute(
                    "SELECT 1 FROM metric_communication_records "
                    "WHERE record_id=%s AND run_id=%s",
                    (ref, checked.run_id),
                ).fetchone():
                    raise ValueError("cross_run_or_missing_pool_reference")
            db.execute(
                "INSERT INTO metric_communication_records(record_id,run_id,record_json) "
                "VALUES (%s,%s,%s)",
                (checked.record_id, checked.run_id, Jsonb(checked.model_dump(mode="json"))),
            )

    def pool_records(self, run_id: str, after_sequence: int = 0, limit: int | None = None):
        with self.connect() as db:
            rows = db.execute(
                "SELECT seq, record_json FROM metric_communication_records "
                "WHERE run_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                (run_id, after_sequence, limit if limit is not None else 2147483647),
            ).fetchall()
        return [dict(row["record_json"], sequence=row["seq"]) for row in rows]

    def finish(self, job_id: str, report: dict | None, error: str | None = None):
        with self.connect() as db:
            status = report["status"] if report else "failed"
            changed = db.execute(
                "UPDATE metric_jobs SET status=%s,report=%s,error=%s "
                "WHERE id=%s AND status='running'",
                (status, Jsonb(report) if report else None, error, job_id),
            ).rowcount
            if changed != 1:
                raise ValueError("invalid_job_transition")
            db.execute(
                "INSERT INTO metric_job_events(job_id,stage,data) VALUES (%s,%s,%s)",
                (job_id, status, Jsonb({})),
            )

    def interrupt(self, job_id: str):
        with self.connect() as db:
            db.execute(
                "UPDATE metric_jobs SET status='interrupted',error='worker_interrupted' "
                "WHERE id=%s AND status='running'",
                (job_id,),
            )

    def recover_interrupted(self):
        with self.connect() as db:
            return db.execute(
                "UPDATE metric_jobs SET status='interrupted',error='worker_interrupted' "
                "WHERE status='running'"
            ).rowcount

    def job(self, job_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT id,round_id,status,report,error FROM metric_jobs WHERE id=%s", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("job_not_found")
            events = db.execute(
                "SELECT seq,stage,created_at FROM metric_job_events "
                "WHERE job_id=%s ORDER BY seq",
                (job_id,),
            ).fetchall()
        return {**row, "events": [
            {**event, "created_at": event["created_at"].isoformat()} for event in events
        ]}
