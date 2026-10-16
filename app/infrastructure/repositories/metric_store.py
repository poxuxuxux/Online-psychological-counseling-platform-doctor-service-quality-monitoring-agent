"""Select a shared PostgreSQL store in deployment and SQLite for local development."""

import os
from pathlib import Path

from app.infrastructure.repositories.local_jobs import LocalJobStore
from app.infrastructure.repositories.postgres_jobs import PostgresJobStore


def build_metric_store(database_url: str):
    if database_url.startswith(("postgresql://", "postgres://")):
        return PostgresJobStore(database_url)
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("APP_ENV", "local").lower() not in (
        "local", "test"
    ):
        raise ValueError("Metric runs need PostgreSQL outside local development")
    return LocalJobStore(Path(os.getenv("LOCAL_JOB_DB", "data/local/jobs.sqlite3")))
