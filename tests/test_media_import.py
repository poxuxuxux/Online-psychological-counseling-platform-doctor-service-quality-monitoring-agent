import json
import subprocess
import wave
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.asr import AsrGateway, MediaError, decode_audio, ffmpeg_path
from app.main import create_app
from tests.conftest import ScriptedModel


async def test_asr_request_contract_and_safe_provider_error(monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", "test-secret")
    def success(request):
        data = json.loads(request.content)
        assert data["model"] == "qwen3-asr-flash"
        assert data["messages"][0]["content"][0]["input_audio"]["data"].startswith("data:audio/flac")
        assert data["asr_options"] == {"enable_itn": False}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "转写测试"}}]})
    gateway = AsrGateway(httpx.MockTransport(success))
    assert await gateway.transcribe("data:audio/flac;base64,AAAA") == "转写测试"
    gateway.transport = httpx.MockTransport(lambda r: httpx.Response(403, text="secret-provider-body"))
    with pytest.raises(MediaError, match="HTTP 403") as error:
        await gateway.transcribe("data:audio/flac;base64,AAAA")
    assert "secret-provider-body" not in str(error.value)


def test_actual_audio_and_video_audio_track_decoding(tmp_path):
    source = tmp_path / "audio.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)
    uri, duration = decode_audio(source.read_bytes(), ".wav")
    assert uri.startswith("data:audio/flac;base64,")
    assert duration == 1
    video = tmp_path / "video.mp4"
    subprocess.run([ffmpeg_path(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=32x32:r=1", "-i", str(source), "-t", "1",
                    "-c:v", "mpeg4", "-c:a", "aac", str(video)], check=True, capture_output=True)
    uri, duration = decode_audio(video.read_bytes(), ".mp4")
    assert uri.startswith("data:audio/flac;base64,")
    assert .9 <= duration <= 1.1
    with pytest.raises(MediaError):
        decode_audio(b"invalid file", ".wav")
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000 * 301)
    with pytest.raises(MediaError, match="最多5分钟"):
        decode_audio(source.read_bytes(), ".wav")


def test_upload_route_uses_audio_only_and_does_not_invent_roles_or_times(tmp_path, monkeypatch, catalog):
    from app.api import media
    monkeypatch.setenv("ASR_API_KEY", "fake-key")
    async def decoded(content, suffix):
        assert content == b"test-video" and suffix == ".mp4"
        return "data:audio/flac;base64,AAAA", 10
    async def transcribed(self, uri):
        return "您好。"
    monkeypatch.setattr(media, "decode_in_background", decoded)
    monkeypatch.setattr(AsrGateway, "transcribe", transcribed)
    settings = replace(Settings(), database_url="sqlite:///" + str(tmp_path / "media.sqlite3"), seed_demo=False)
    with TestClient(create_app(settings=settings, model=ScriptedModel(), catalog=catalog)) as client:
        response = client.post("/api/v1/media/transcribe?format=.mp4", content=b"test-video")
        assert response.status_code == 200
        body = response.json()
        assert body["source_modality"] == "video" and body["text"] == "您好。"
        assert body["timestamps_available"] is False
        assert "role" not in body
        assert client.post("/api/v1/media/transcribe?format=.exe", content=b"test").status_code == 422
        monkeypatch.setattr(media, "MAX_UPLOAD", 4)
        assert client.post("/api/v1/media/transcribe?format=.wav", content=b"12345").status_code == 413
        monkeypatch.delenv("ASR_API_KEY")
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        response = client.post("/api/v1/media/transcribe?format=.wav", content=b"test")
        assert response.status_code == 503
