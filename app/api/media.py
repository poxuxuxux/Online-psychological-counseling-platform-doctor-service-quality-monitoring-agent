import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.infrastructure.asr import (
    FORMATS,
    MAX_UPLOAD,
    VIDEO,
    AsrGateway,
    MediaError,
    decode_in_background,
)

router = APIRouter()


@router.post("/api/v1/media/transcribe")
async def transcribe(request: Request, format: str = Query(..., max_length=8)):
    suffix = format.lower()
    if suffix not in FORMATS:
        raise HTTPException(422, "Unsupported media format")
    gateway = AsrGateway()
    if not gateway.key:
        return JSONResponse(status_code=503, content={"error": "请在后端配置 DASHSCOPE_API_KEY 或 ASR_API_KEY。"})
    # Per-app rate and concurrency limits also apply to unauthenticated uploads.
    state = request.app.state
    current = time.monotonic()
    state.asr_requests[:] = [t for t in state.asr_requests if current - t < 3600]
    if len(state.asr_requests) >= 30 or state.asr_active >= 2:
        raise HTTPException(429, "Transcription capacity reached")
    state.asr_requests.append(current)
    state.asr_active += 1
    try:
        data = bytearray()
        async with asyncio.timeout(60):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_UPLOAD:
                    raise HTTPException(413, "Media exceeds 64 MiB")
                data.extend(chunk)
        if not data:
            raise HTTPException(422, "Empty media")
        audio, duration = await decode_in_background(bytes(data), suffix)
        text = await gateway.transcribe(audio)
        return {"text": text, "duration_seconds": duration, "model": gateway.model,
                "source_modality": "video" if suffix in VIDEO else "audio",
                "timestamps_available": False}
    except MediaError as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    except TimeoutError:
        return JSONResponse(status_code=408, content={"error": "媒体上传超时，请重试。"})
    finally:
        state.asr_active -= 1
