# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/local/teams.sqlite3"
    api_token: str = ""
    frontend_origins: tuple[str, ...] = ()
    skill_dir: Path = Path(__file__).parent / "rubrics" / "metrics"
    max_steps: int = 24
    max_rounds: int = 40
    max_messages: int = 60
    max_reviews: int = 6
    max_revisions: int = 2
    concurrency: int = 6
    max_model_calls: int = 180
    max_input_chars: int = 4_000_000
    agent_timeout: float = 180
    model_timeout: float = 60
    total_timeout: float = 600
    seed_demo: bool = True
    bucket: str = ""
    bucket_endpoint: str = ""
    bucket_region: str = ""
    bucket_access_key: str = ""
    bucket_secret_key: str = ""
    bucket_encryption_key: str = ""

    @staticmethod
    def frontend_origins_from_env():
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
            if origin.strip()
        )
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or origin == "*"
            ):
                raise ValueError("FRONTEND_ORIGINS must contain exact HTTP(S) origins")
        return origins

    @classmethod
    def from_env(cls):
        app_env = os.getenv("APP_ENV", "local")
        db = os.getenv("DATABASE_URL", "").strip()
        if app_env not in {"local", "test"} and not db.startswith(("postgresql://", "postgres://")):
            raise ValueError("Production requires Railway PostgreSQL DATABASE_URL")
        settings = cls(
            database_url=db or cls.database_url,
            api_token=os.getenv("EVALUATION_API_TOKEN", ""),
            frontend_origins=cls.frontend_origins_from_env(),
            skill_dir=Path(os.getenv("METRIC_SKILLS_DIR", str(cls.skill_dir))),
            **{
                field: int(os.getenv("TEAM_" + field.upper(), str(getattr(cls, field))))
                for field in (
                    "max_steps",
                    "max_rounds",
                    "max_messages",
                    "max_reviews",
                    "max_revisions",
                    "concurrency",
                    "max_model_calls",
                    "max_input_chars",
                )
            },
            **{
                field: float(os.getenv("TEAM_" + field.upper(), str(getattr(cls, field))))
                for field in ("agent_timeout", "model_timeout", "total_timeout")
            },
            seed_demo=os.getenv(
                "SEED_DEMO", "true" if app_env in {"local", "test"} else "false"
            ).lower()
            == "true",
            bucket=os.getenv("BUCKET", "").strip(),
            bucket_endpoint=os.getenv("ENDPOINT", "").strip(),
            bucket_region=os.getenv("REGION", "").strip(),
            bucket_access_key=os.getenv("ACCESS_KEY_ID", "").strip(),
            bucket_secret_key=os.getenv("SECRET_ACCESS_KEY", "").strip(),
            bucket_encryption_key=os.getenv("BUCKET_ENCRYPTION_KEY", "").strip(),
        )
        bucket_values = (
            settings.bucket,
            settings.bucket_endpoint,
            settings.bucket_region,
            settings.bucket_access_key,
            settings.bucket_secret_key,
        )
        if any(bucket_values) and not all(bucket_values):
            raise ValueError("Bucket requires BUCKET, ENDPOINT, REGION and both access keys")
        if all(bucket_values) and not settings.bucket_encryption_key:
            raise ValueError("Bucket storage requires BUCKET_ENCRYPTION_KEY")
        if any(
            getattr(settings, key) <= 0
            for key in (
                "max_steps",
                "max_rounds",
                "max_messages",
                "max_reviews",
                "max_revisions",
                "concurrency",
                "max_model_calls",
                "max_input_chars",
                "agent_timeout",
                "model_timeout",
                "total_timeout",
            )
        ):
            raise ValueError("Team budgets must be positive")
        return settings
