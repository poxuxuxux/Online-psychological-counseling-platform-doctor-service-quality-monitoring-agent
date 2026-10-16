"""Bailian OpenAI-compatible text transport; never log prompts, keys or response bodies."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx


class ModelCallError(RuntimeError):
    """Safe error code suitable for a task record; provider bodies remain private."""


@dataclass(frozen=True)
class QwenConfig:
    api_key: str = field(repr=False)
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen3.5-plus"
    timeout_seconds: float = 90
    max_tokens: int = 4096

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if not self.api_key.strip():
            raise ValueError("DASHSCOPE_API_KEY is required")
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("QWEN_BASE_URL must be an HTTPS base URL")
        if self.timeout_seconds <= 0 or self.max_tokens < 1:
            raise ValueError("Model timeout and token budget must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            base_url=os.getenv("QWEN_BASE_URL", cls.base_url),
            model=os.getenv("QWEN_MODEL", cls.model),
            timeout_seconds=float(os.getenv("QWEN_TIMEOUT_SECONDS", "90")),
            max_tokens=int(os.getenv("QWEN_MAX_TOKENS", "4096")),
        )


class QwenProvider:
    """Implements LLMProvider. No implicit retries or fallback to demo scores."""

    def __init__(self, config: QwenConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self._transport = transport

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        return await self._complete(system_prompt, user_prompt, json_mode=False)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        return await self._complete(system_prompt, user_prompt, json_mode=True)

    async def _complete(self, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "enable_thinking": False,
            "max_tokens": self.config.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.config.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.config.api_key},
                    json=payload,
                )
        except httpx.TimeoutException:
            raise ModelCallError("model_timeout") from None
        except httpx.RequestError:
            raise ModelCallError("model_connection_failed") from None
        if response.status_code != 200:
            raise ModelCallError(f"model_http_{response.status_code}")
        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop":
                raise ModelCallError("model_incomplete_response")
            if not isinstance(content, str) or not content.strip():
                raise ModelCallError("model_empty_response")
            return content
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelCallError("model_invalid_response") from None
