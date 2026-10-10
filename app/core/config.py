"""功能：读取运行环境配置，并集中提供带安全默认值的应用设置。"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """应用级配置；敏感密钥应从环境变量注入，不写入代码或仓库。"""

    app_name: str = "psychological-service-quality-agent"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/local/app.sqlite3"
    enable_cross_session_memory: bool = False


def get_settings() -> Settings:
    """根据环境变量构造配置；记忆功能默认关闭，需显式配置才能开启。"""
    memory_enabled = os.getenv("ENABLE_CROSS_SESSION_MEMORY", "false").lower() == "true"
    return Settings(
        app_name=os.getenv("APP_NAME", "psychological-service-quality-agent"),
        app_env=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/local/app.sqlite3"),
        enable_cross_session_memory=memory_enabled,
    )
