"""功能：集中判断是否允许患者跨会话记忆；默认关闭且不推测患者身份。"""

from app.core.config import Settings


class MemoryPolicy:
    """在读取任何患者记忆前执行的策略门；实现不等于已获得数据使用授权。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def may_use_cross_session_memory(self, has_trusted_patient_ref: bool) -> bool:
        """仅在功能开关开启且存在可信匿名映射时返回允许。"""
        return self._settings.enable_cross_session_memory and has_trusted_patient_ref
