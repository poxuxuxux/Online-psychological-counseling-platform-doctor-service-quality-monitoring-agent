"""Bounded local media decoding and Qwen3-ASR audio transcription."""
import asyncio
import base64
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from urllib.parse import urlsplit

import httpx

FORMATS = {".wav": "wav", ".mp3": "mp3", ".m4a": "mov", ".mp4": "mov", ".mov": "mov",
           ".mkv": "matroska", ".webm": "matroska", ".ogg": "ogg", ".opus": "ogg",
           ".flac": "flac", ".aac": "aac", ".avi": "avi"}
VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
MAX_UPLOAD = 64 * 1024 * 1024


class MediaError(ValueError):
    pass


def ffmpeg_path():
    configured = os.getenv("ASR_FFMPEG_PATH") or shutil.which("ffmpeg")
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise MediaError("音视频解码器未安装，请安装项目最新 requirements.txt。") from None


def decode_audio(content: bytes, suffix: str):
    executable = ffmpeg_path()
    with tempfile.TemporaryDirectory(prefix="xin-jian-asr-") as folder:
        source, wav, flac = [Path(folder) / name for name in ("source" + suffix, "audio.wav", "audio.flac")]
        source.write_bytes(content)
        common = [executable, "-nostdin", "-hide_banner", "-loglevel", "error",
                  "-protocol_whitelist", "file,pipe"]
        commands = [
            [*common, "-f", FORMATS[suffix], "-i", str(source), "-map", "0:a:0",
             "-vn", "-t", "301", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            [*common, "-i", str(wav), "-c:a", "flac", str(flac)],
        ]
        try:
            subprocess.run(commands[0], check=True, capture_output=True, timeout=60)
            with wave.open(str(wav), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            if not 0 < duration <= 300:
                raise MediaError("每个文件支持最多5分钟，请按真实话轮拆分长录音后上传。")
            subprocess.run(commands[1], check=True, capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError, wave.Error):
            raise MediaError("无法读取音轨，请检查媒体格式、音轨及文件是否完整。") from None
        encoded = base64.b64encode(flac.read_bytes()).decode("ascii")
        if len(encoded) > 9_500_000:
            raise MediaError("音轨编码后过大，请拆分录音后上传。")
        return "data:audio/flac;base64," + encoded, duration


class AsrGateway:
    def __init__(self, transport=None):
        self.key = os.getenv("ASR_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = os.getenv("ASR_MODEL", "qwen3-asr-flash")
        self.base = os.getenv("ASR_BASE_URL") or os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.transport = transport

    async def transcribe(self, audio_uri):
        parsed = urlsplit(self.base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise MediaError("ASR_BASE_URL 必须是有效的 HTTPS API 地址。")
        body = {"model": self.model, "stream": False,
                "messages": [{"role": "user", "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_uri}}]}],
                "asr_options": {"enable_itn": False}}
        try:
            async with httpx.AsyncClient(timeout=120, transport=self.transport, follow_redirects=False) as client:
                response = await client.post(self.base.rstrip("/") + "/chat/completions",
                                             headers={"Authorization": "Bearer " + self.key}, json=body)
                response.raise_for_status()
                data = response.json()
                if data["choices"][0].get("finish_reason") != "stop":
                    raise MediaError("转写未完整返回，请拆分文件后重试。")
                text = data["choices"][0]["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    raise MediaError("未识别到有效讲话，请检查音轨。")
                return text.strip()
        except httpx.TimeoutException:
            raise MediaError("转写服务超时，请稍后重试。") from None
        except httpx.HTTPStatusError as exc:
            raise MediaError(f"转写服务返回 HTTP {exc.response.status_code}，请检查 ASR 密钥、地域及模型权限。") from None
        except httpx.RequestError:
            raise MediaError("无法连接转写服务，请检查后端网络。") from None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            if isinstance(exc, MediaError):
                raise
            raise MediaError("转写服务返回格式不兼容。") from None


async def decode_in_background(content, suffix):
    # Keep the concurrency slot until decoding ends even if a browser disconnects.
    task = asyncio.create_task(asyncio.to_thread(decode_audio, content, suffix))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
