"""功能：音视频转写适配器；未接入真实 ASR 引擎前显式失败。"""

from app.domain.models import MediaAsset, TranscriptInfo


class UnconfiguredTranscriber:
    """占位转写器；避免未配置引擎时生成看似真实的转写内容。"""

    engine_name = "unconfigured"
    engine_version = "0.0.0"

    async def transcribe(self, media: MediaAsset) -> TranscriptInfo:
        """拒绝转写并显式报错；接入真实引擎时替换本类并记录引擎版本。"""
        raise NotImplementedError(
            f"No ASR provider configured for media {media.media_id}; "
            "register a Transcriber implementation before importing multimodal sessions"
        )
