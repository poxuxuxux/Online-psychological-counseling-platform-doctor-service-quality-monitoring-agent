"""功能：原始媒体的本地受控存储实现；生产环境需加密与访问控制。"""

from pathlib import Path
from typing import Literal


class LocalMediaStorage:
    """把媒体写入受控目录并校验读取引用，防止路径穿越。"""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        media_id: str,
        data: bytes,
        modality: Literal["audio", "video"],
        mime_type: str | None = None,
    ) -> str:
        """按白名单文件名保存媒体；media_id 只允许安全字符集。"""
        safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in media_id)
        path = self._directory / f"{modality}-{safe_id}"
        path.write_bytes(data)
        return str(path.relative_to(self._directory))

    async def read(self, storage_ref: str) -> bytes:
        """读取媒体；引用必须解析到受控目录内，否则拒绝。"""
        path = (self._directory / storage_ref).resolve()
        if self._directory.resolve() not in path.parents:
            raise PermissionError(f"Media reference escapes storage directory: {storage_ref}")
        return path.read_bytes()
