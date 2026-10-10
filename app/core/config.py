"""功能：读取运行环境配置，并集中提供带安全默认值的应用设置。"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """应用级配置；敏感密钥应从环境变量注入，不写入代码或仓库。"""

    app_name: str = "psychological-service-quality-agent"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/local/app.sqlite3"
    enable_cross_session_memory: bool = False
    media_storage_dir: str = "./data/local/media"
    agent_timeout_seconds: float = 120.0
    max_agent_concurrency: int = 3
    min_transcript_confidence: float = 0.6
    max_unknown_role_ratio: float = 0.5


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_settings() -> Settings:
    """根据环境变量构造配置；记忆功能默认关闭，需显式配置才能开启。"""
    memory_enabled = os.getenv("ENABLE_CROSS_SESSION_MEMORY", "false").lower() == "true"
    return Settings(
        app_name=_env_str("APP_NAME", "psychological-service-quality-agent"),
        app_env=_env_str("APP_ENV", "local"),
        database_url=_env_str("DATABASE_URL", "sqlite:///./data/local/app.sqlite3"),
        enable_cross_session_memory=memory_enabled,
        media_storage_dir=_env_str("MEDIA_STORAGE_DIR", "./data/local/media"),
        agent_timeout_seconds=_env_float("AGENT_TIMEOUT_SECONDS", 120.0),
        max_agent_concurrency=_env_int("MAX_AGENT_CONCURRENCY", 3),
        min_transcript_confidence=_env_float("MIN_TRANSCRIPT_CONFIDENCE", 0.6),
        max_unknown_role_ratio=_env_float("MAX_UNKNOWN_ROLE_RATIO", 0.5),
    )
