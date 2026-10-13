"""功能：将合成演示会话和评价报告持久化到 PostgreSQL。"""

from typing import Any

from app.domain.models import ConversationSession, EvaluationReport


class PostgresEvaluationStore:
    """最小 PostgreSQL 存储适配器；正式版本可替换为迁移工具管理的仓储。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url.strip()

    @property
    def configured(self) -> bool:
        """仅把 PostgreSQL URL 视为已配置，避免误用本地 SQLite 默认值。"""
        return self._database_url.startswith(("postgresql://", "postgres://"))

    async def initialize(self) -> None:
        """创建最小演示表；重复启动不会覆盖已有数据。"""
        if not self.configured:
            return
        async with await self._connect() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consultation_sessions (
                    session_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    session_data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_reports (
                    evaluation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES consultation_sessions(session_id),
                    status TEXT NOT NULL,
                    report_data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    async def readiness(self) -> dict[str, Any]:
        """执行真实查询，区分未配置与已连接。"""
        if not self.configured:
            return {
                "configured": False,
                "connected": False,
                "detail": "DATABASE_URL is not linked to PostgreSQL",
            }
        try:
            async with await self._connect() as connection:
                cursor = await connection.execute("SELECT current_database(), NOW()")
                database_name, checked_at = await cursor.fetchone()
        except Exception as error:  # noqa: BLE001 - 就绪接口需要返回可诊断状态
            return {"configured": True, "connected": False, "detail": str(error)}
        return {
            "configured": True,
            "connected": True,
            "database": database_name,
            "checked_at": checked_at.isoformat(),
        }

    async def save_session(self, session: ConversationSession) -> None:
        """按会话 ID 幂等保存合成会话。"""
        if not self.configured:
            return
        from psycopg.types.json import Jsonb

        async with await self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO consultation_sessions (session_id, source_id, session_data)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    session_data = EXCLUDED.session_data,
                    updated_at = NOW()
                """,
                (session.session_id, session.source_id, Jsonb(session.model_dump(mode="json"))),
            )

    async def save_report(self, report: EvaluationReport) -> None:
        """保存每次运行的完整结构化报告，不覆盖其他 evaluation_id。"""
        if not self.configured:
            return
        from psycopg.types.json import Jsonb

        async with await self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO evaluation_reports (evaluation_id, session_id, status, report_data)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    report.evaluation_id,
                    report.session_id,
                    report.status,
                    Jsonb(report.model_dump(mode="json")),
                ),
            )

    async def recent_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        """返回最近报告摘要，供演示确认服务重启后数据仍存在。"""
        if not self.configured:
            return []
        async with await self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT evaluation_id, session_id, status, created_at
                FROM evaluation_reports
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [
            {
                "evaluation_id": row[0],
                "session_id": row[1],
                "status": row[2],
                "created_at": row[3].isoformat(),
            }
            for row in rows
        ]

    async def overview_records(self, start, end) -> list[dict[str, Any]]:
        """Read latest report per round, then filter; no consultation text leaves this API."""
        if not self.configured:
            return []
        async with await self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT r.evaluation_id, r.session_id, r.report_data, r.created_at, s.source_id
                FROM (
                    SELECT DISTINCT ON (session_id)
                           evaluation_id, session_id, report_data, created_at
                    FROM evaluation_reports
                    ORDER BY session_id, created_at DESC, evaluation_id DESC
                ) r
                JOIN consultation_sessions s ON s.session_id = r.session_id
                WHERE r.created_at >= %s AND r.created_at < %s
                ORDER BY r.created_at DESC, r.evaluation_id DESC
                """,
                (start, end),
            )
            rows = await cursor.fetchall()
        return [
            {
                "evaluation_id": r[0],
                "session_id": r[1],
                "report_data": r[2],
                "created_at": r[3],
                "source_id": r[4],
            }
            for r in rows
        ]

    async def list_consultations(self, limit: int, offset: int, query: str) -> dict[str, Any]:
        """Public demo reads only synthetic rows; real consultations need platform access control."""
        if not self.configured:
            return {"database_configured": False, "total": 0, "items": []}
        async with await self._connect() as connection:
            count_cursor = await connection.execute(
                """SELECT COUNT(*) FROM consultation_sessions
                   WHERE source_id = 'synthetic-demo' AND POSITION(%s IN session_id) > 0""",
                (query,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await connection.execute(
                """
                SELECT s.session_id, s.session_data, s.updated_at, r.status
                FROM consultation_sessions s
                LEFT JOIN LATERAL (
                    SELECT status FROM evaluation_reports
                    WHERE session_id = s.session_id
                    ORDER BY created_at DESC, evaluation_id DESC LIMIT 1
                ) r ON TRUE
                WHERE s.source_id = 'synthetic-demo' AND POSITION(%s IN s.session_id) > 0
                ORDER BY s.updated_at DESC, s.session_id DESC
                LIMIT %s OFFSET %s
                """,
                (query, limit, offset),
            )
            rows = await cursor.fetchall()
        items = []
        for row in rows:
            session = ConversationSession.model_validate(row[1])
            if session.session_id != row[0] or session.source_id != "synthetic-demo":
                raise ValueError("Stored session metadata mismatch")
            items.append({"session_id": row[0], "consultation_round": session.consultation_round,
                          "message_count": len(session.messages), "updated_at": row[2].isoformat(),
                          "evaluation_status": row[3]})
        return {"database_configured": True, "total": total, "items": items}

    async def consultation_detail(self, session_id: str) -> dict[str, Any] | None:
        """Load the session and latest report together, including sessions not yet evaluated."""
        if not self.configured:
            return None
        async with await self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT s.session_data, r.report_data
                FROM consultation_sessions s
                LEFT JOIN LATERAL (
                    SELECT report_data FROM evaluation_reports
                    WHERE session_id = s.session_id
                    ORDER BY created_at DESC, evaluation_id DESC LIMIT 1
                ) r ON TRUE
                WHERE s.session_id = %s AND s.source_id = 'synthetic-demo'
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        session = ConversationSession.model_validate(row[0])
        if session.session_id != session_id or session.source_id != "synthetic-demo":
            raise ValueError("Stored session metadata mismatch")
        report = EvaluationReport.model_validate(row[1]) if row[1] is not None else None
        if report is not None and report.session_id != session_id:
            raise ValueError("Stored report/session mismatch")
        # Preserve optional presentation fields stored by future backend versions.
        return {"session": session.model_dump(mode="json"), "report": row[1]}

    async def _connect(self):
        """延迟导入驱动，使未配置数据库的本地测试仍可独立运行。"""
        from psycopg import AsyncConnection

        return await AsyncConnection.connect(self._database_url)
