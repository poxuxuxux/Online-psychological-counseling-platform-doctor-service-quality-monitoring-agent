# 环节：基础设施适配层；用途：封装模型、数据库或用量遥测等外部能力。
"""Versioned additive tables, durable snapshots, leases and transactional audit writes.

Production uses the existing DATABASE_URL/psycopg driver. SQLite is a local/test adapter.
No legacy platform table is altered or deleted.
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from app.domain.models import now


class RunBusy(RuntimeError):
    pass


class Repository:
    def __init__(self, url: str):
        self.postgres = url.startswith(("postgresql://", "postgres://"))
        self.url = url
        if not self.postgres and not url.startswith("sqlite:///"):
            raise ValueError("DATABASE_URL must use PostgreSQL or explicit local SQLite")
        if not self.postgres:
            self.path = Path(url.removeprefix("sqlite:///"))
            self.path.parent.mkdir(parents=True, exist_ok=True)

    async def _transaction(self, statements):
        if self.postgres:
            from psycopg import AsyncConnection

            async with await AsyncConnection.connect(self.url, connect_timeout=10) as db:
                output = []
                for sql, params in statements:
                    cursor = await db.execute(sql.replace("?", "%s"), params)
                    output.append(
                        await cursor.fetchall() if cursor.description else cursor.rowcount
                    )
                return output
        return await asyncio.to_thread(self._sqlite_transaction, statements)

    def _sqlite_transaction(self, statements):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                output = []
                for sql, params in statements:
                    cursor = db.execute(sql, params)
                    output.append(cursor.fetchall() if cursor.description else cursor.rowcount)
                return output
        finally:
            db.close()

    async def initialize(self):
        statements = [
            (
                """CREATE TABLE IF NOT EXISTS team_sessions (
              session_id TEXT PRIMARY KEY, patient_id TEXT, doctor_id TEXT, session_time TEXT,
              source_id TEXT, payload TEXT NOT NULL, updated_at TEXT NOT NULL)""",
                (),
            ),
            (
                """CREATE INDEX IF NOT EXISTS team_session_relation
              ON team_sessions(patient_id,doctor_id,session_time)""",
                (),
            ),
            (
                """CREATE TABLE IF NOT EXISTS team_runs (
              run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES team_sessions(session_id),
              status TEXT NOT NULL, payload TEXT NOT NULL, report TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, lease_owner TEXT, lease_until DOUBLE PRECISION NOT NULL
              DEFAULT 0)""",
                (),
            ),
        ]
        for table in ("team_tasks", "team_evidence", "team_messages", "team_events"):
            statements.append(
                (
                    f"""CREATE TABLE IF NOT EXISTS {table} (
              run_id TEXT NOT NULL REFERENCES team_runs(run_id), artifact_id TEXT NOT NULL,
              payload TEXT NOT NULL, PRIMARY KEY(run_id,artifact_id))""",
                    (),
                )
            )
        statements.append(
            (
                """CREATE TABLE IF NOT EXISTS team_human_reviews (
          review_id TEXT PRIMARY KEY, evaluation_id TEXT NOT NULL REFERENCES team_runs(run_id),
          payload TEXT NOT NULL)""",
                (),
            )
        )
        await self._transaction(statements)

    async def readiness(self):
        try:
            await self._transaction([("SELECT 1 FROM team_runs LIMIT 1", ())])
            return {
                "configured": True,
                "connected": True,
                "backend": "postgresql" if self.postgres else "sqlite",
                "checked_at": now(),
            }
        except Exception:  # noqa: BLE001 - readiness must not leak database credentials/errors
            return {"configured": True, "connected": False, "detail": "database_unavailable"}

    async def save_session(self, session: dict):
        # Immutable input prevents later reports being paired with changed original dialogue.
        data = json.dumps(session, sort_keys=True, ensure_ascii=False)
        await self._transaction(
            [
                (
                    """INSERT INTO team_sessions
          (session_id,patient_id,doctor_id,session_time,source_id,payload,updated_at)
          VALUES (?,?,?,?,?,?,?) ON CONFLICT(session_id) DO NOTHING""",
                    (
                        session["session_id"],
                        session.get("patient_id"),
                        session.get("doctor_id"),
                        session.get("session_time"),
                        session.get("source_id"),
                        data,
                        now(),
                    ),
                )
            ]
        )
        existing = await self.session(session["session_id"])
        if existing != session:
            raise ValueError("session_id already belongs to different immutable input")

    async def session(self, session_id):
        rows = (
            await self._transaction(
                [("SELECT payload FROM team_sessions WHERE session_id=?", (session_id,))]
            )
        )[0]
        return json.loads(rows[0][0]) if rows else None

    async def history(self, session: dict, limit=20):
        if not all(session.get(k) for k in ("patient_id", "doctor_id", "session_time")):
            return []
        rows = (
            await self._transaction(
                [
                    (
                        """SELECT s.payload,
          (SELECT r.report FROM team_runs r WHERE r.session_id=s.session_id AND r.report IS NOT NULL
           ORDER BY r.created_at DESC,r.run_id DESC LIMIT 1)
          FROM team_sessions s WHERE s.patient_id=? AND s.doctor_id=?
          AND s.session_id<>? AND s.session_time<? ORDER BY s.session_time DESC,s.session_id DESC
          LIMIT ?""",
                        (
                            session["patient_id"],
                            session["doctor_id"],
                            session["session_id"],
                            session["session_time"],
                            limit,
                        ),
                    )
                ]
            )
        )[0]
        return [
            {"session": json.loads(row[0]), "report": json.loads(row[1]) if row[1] else None}
            for row in rows
        ]

    async def create_run(self, state):
        await self._transaction(
            [
                (
                    """INSERT INTO team_runs
          (run_id,session_id,status,payload,created_at,updated_at) VALUES (?,?,?,?,?,?)""",
                    (
                        state["run_id"],
                        state["session"]["session_id"],
                        "pending",
                        json.dumps(state, ensure_ascii=False),
                        now(),
                        now(),
                    ),
                )
            ]
        )

    async def get_run(self, run_id):
        rows = (
            await self._transaction([("SELECT payload FROM team_runs WHERE run_id=?", (run_id,))])
        )[0]
        return json.loads(rows[0][0]) if rows else None

    async def claim(self, run_id, owner, seconds):
        changed = (
            await self._transaction(
                [
                    (
                        """UPDATE team_runs SET lease_owner=?,lease_until=?
          WHERE run_id=? AND lease_until<?""",
                        (owner, time.time() + seconds, run_id, time.time()),
                    )
                ]
            )
        )[0]
        return changed == 1

    async def checkpoint(self, state, owner):
        # CAS/lease check and snapshots + artifacts share one database transaction.
        # Lease ownership is checked by guarding every artifact INSERT against the run row.
        statements = [
            (
                """UPDATE team_runs SET payload=?,report=?,status=?,updated_at=?
          WHERE run_id=? AND lease_owner=? AND lease_until>?""",
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(state["report"], ensure_ascii=False)
                    if state.get("report")
                    else None,
                    state.get("status", "running"),
                    now(),
                    state["run_id"],
                    owner,
                    time.time(),
                ),
            )
        ]
        for key, table, id_key in (
            ("tasks", "team_tasks", "task_id"),
            ("evidence", "team_evidence", "evidence_id"),
            ("messages", "team_messages", "message_id"),
            ("events", "team_events", "event_id"),
        ):
            items = state.get("team", {}).get(key, {})
            for item in items.values() if isinstance(items, dict) else items:
                statements.append(
                    (
                        f"""INSERT INTO {table}(run_id,artifact_id,payload)
                  SELECT ?,?,? WHERE EXISTS(SELECT 1 FROM team_runs
                  WHERE run_id=? AND lease_owner=? AND lease_until>?)
                  ON CONFLICT(run_id,artifact_id) DO UPDATE SET payload=excluded.payload""",
                        (
                            state["run_id"],
                            item[id_key],
                            json.dumps(item, ensure_ascii=False),
                            state["run_id"],
                            owner,
                            time.time(),
                        ),
                    )
                )
        if (await self._transaction(statements))[0] != 1:
            raise RunBusy("run_lease_lost")

    async def release(self, run_id, owner):
        await self._transaction(
            [
                (
                    "UPDATE team_runs SET lease_until=0 WHERE run_id=? AND lease_owner=?",
                    (run_id, owner),
                )
            ]
        )

    async def recent(self, limit=20, public=True):
        rows = (
            await self._transaction(
                [
                    (
                        """SELECT r.run_id,r.session_id,r.status,r.created_at
          FROM team_runs r JOIN team_sessions s ON s.session_id=r.session_id
          WHERE r.report IS NOT NULL AND (?=0 OR s.source_id='synthetic-demo')
          ORDER BY r.created_at DESC LIMIT ?""",
                        (int(public), limit),
                    )
                ]
            )
        )[0]
        return [
            {"evaluation_id": r[0], "session_id": r[1], "status": r[2], "created_at": r[3]}
            for r in rows
        ]

    async def consultations(self, limit, offset, query, public=True):
        where = "(?=0 OR s.source_id='synthetic-demo') AND s.session_id LIKE ?"
        params = (int(public), "%" + query + "%")
        count, rows = await self._transaction(
            [
                (f"SELECT COUNT(*) FROM team_sessions s WHERE {where}", params),
                (
                    f"""SELECT s.payload,s.updated_at,(SELECT r.status FROM team_runs r
              WHERE r.session_id=s.session_id AND r.report IS NOT NULL
              ORDER BY r.created_at DESC LIMIT 1) FROM team_sessions s WHERE {where}
              ORDER BY s.updated_at DESC,s.session_id LIMIT ? OFFSET ?""",
                    (*params, limit, offset),
                ),
            ]
        )
        items = []
        for payload, updated, status in rows:
            session = json.loads(payload)
            items.append(
                {
                    "session_id": session["session_id"],
                    "consultation_round": session["consultation_round"],
                    "message_count": len(session["messages"]),
                    "updated_at": updated,
                    "evaluation_status": status,
                }
            )
        return {"database_configured": True, "total": count[0][0], "items": items}

    async def detail(self, session_id):
        session = await self.session(session_id)
        if session is None:
            return None
        rows = (
            await self._transaction(
                [
                    (
                        """SELECT report FROM team_runs WHERE session_id=?
          AND report IS NOT NULL ORDER BY created_at DESC,run_id DESC LIMIT 1""",
                        (session_id,),
                    )
                ]
            )
        )[0]
        report = json.loads(rows[0][0]) if rows else None
        if report:
            session["consultation_round"] = report["session_type"].lower()
        return {"session": session, "report": report}

    async def add_review(self, review):
        await self._transaction(
            [
                (
                    "INSERT INTO team_human_reviews VALUES (?,?,?)",
                    (
                        review["review_id"],
                        review["evaluation_id"],
                        json.dumps(review, ensure_ascii=False),
                    ),
                )
            ]
        )

    async def reviews(self, run_id):
        rows = (
            await self._transaction(
                [("SELECT payload FROM team_human_reviews WHERE evaluation_id=?", (run_id,))]
            )
        )[0]
        return [json.loads(row[0]) for row in rows]

    async def latest_reports(self, public=True):
        rows = (
            await self._transaction(
                [
                    (
                        """SELECT r.report,s.source_id FROM team_runs r
          JOIN team_sessions s ON s.session_id=r.session_id
          WHERE r.report IS NOT NULL AND (?=0 OR s.source_id='synthetic-demo')
          AND r.run_id=(SELECT r2.run_id FROM team_runs r2 WHERE r2.session_id=r.session_id
                       AND r2.report IS NOT NULL ORDER BY r2.created_at DESC,r2.run_id DESC LIMIT 1)""",
                        (int(public),),
                    )
                ]
            )
        )[0]
        return [{**json.loads(row[0]), "source_id": row[1]} for row in rows]
