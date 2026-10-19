# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/local/teams.sqlite3"
    api_token: str = ""
    skill_dir: Path = Path(__file__).parent / "rubrics" / "metrics"
    max_steps: int = 24
    max_rounds: int = 40
    max_messages: int = 60
    max_reviews: int = 6
    max_revisions: int = 2
    concurrency: int = 6
    max_model_calls: int = 180
    agent_timeout: float = 180
    model_timeout: float = 60
    total_timeout: float = 600
    seed_demo: bool = True

    @classmethod
    def from_env(cls):
        app_env = os.getenv("APP_ENV", "local")
        db = os.getenv("DATABASE_URL", "").strip()
        if app_env not in {"local", "test"} and not db.startswith(("postgresql://", "postgres://")):
            raise ValueError("Production requires Railway PostgreSQL DATABASE_URL")
        settings = cls(
            database_url=db or cls.database_url,
            api_token=os.getenv("EVALUATION_API_TOKEN", ""),
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
        )
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
                "agent_timeout",
                "model_timeout",
                "total_timeout",
            )
        ):
            raise ValueError("Team budgets must be positive")
        return settings
