# 环节：基础设施适配层；用途：封装模型、数据库或用量遥测等外部能力。
"""DeepSeek/Qwen/GLM JSON tool-decision gateway. Secrets and provider bodies never enter logs."""

import json
import logging
import os
import re
import time
from urllib.parse import urlsplit

import httpx

from app.domain.ports import ModelUnavailable
from app.infrastructure.telemetry import model_usage

log = logging.getLogger(__name__)


def transport_diagnostics(error, endpoint_host):
    """Exception classes only: never expose URLs with credentials, headers or response bodies."""
    causes, seen = [], set()
    current = error
    while current is not None and id(current) not in seen and len(causes) < 8:
        seen.add(id(current))
        causes.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    if isinstance(error, httpx.ProxyError):
        category = "proxy"
    elif any("SSL" in name or "Certificate" in name for name in causes):
        category = "tls"
    elif "gaierror" in causes:
        category = "dns"
    elif isinstance(error, httpx.TimeoutException):
        category = "timeout"
    elif isinstance(error, httpx.RemoteProtocolError):
        category = "remote_protocol"
    elif isinstance(error, httpx.ConnectError):
        category = "connect"
    elif isinstance(error, (httpx.ReadError, httpx.WriteError)):
        category = "read_write"
    else:
        category = "transport"
    return {"category": category, "exception_type": type(error).__name__,
            "cause_types": causes, "endpoint_host": endpoint_host}

PROVIDERS = {
    "deepseek": {
        "key": "DEEPSEEK_API_KEY",
        "prefix": "DEEPSEEK",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "key": "DASHSCOPE_API_KEY",
        "prefix": "QWEN",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.5-plus",
    },
    "glm": {
        "key": "GLM_API_KEY",
        "prefix": "GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
    },
}


def _decode_object(content):
    if not isinstance(content, str):
        raise TypeError("Model content must be text")
    fenced = re.fullmatch(r"\s*```(?:json)?\s*([\s\S]*?)\s*```\s*", content)
    if fenced:
        content = fenced[1]
    try:
        return json.loads(content), bool(fenced), None
    except json.JSONDecodeError as error:
        # Only recover container delimiters at the end. Never edit claims, scores,
        # quoted evidence or an error in the middle of the model's answer.
        if error.msg == "Extra data":
            result, end = json.JSONDecoder().raw_decode(content.lstrip())
            if content.lstrip()[end:].strip("} \t\r\n") == "":
                return result, bool(fenced), "extra_closing_brace"
        if error.pos == len(content):
            stack = []
            quoted = escaped = False
            for char in content:
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in "{[":
                    stack.append("}" if char == "{" else "]")
                elif char in "}]" and (not stack or stack.pop() != char):
                    break
            else:
                if not quoted and stack:
                    try:
                        return json.loads(content + "".join(reversed(stack))), bool(fenced), "missing_closing_brace"
                    except json.JSONDecodeError:
                        pass
        raise


class JsonModelGateway:
    def __init__(self, transport=None):
        self.provider = next(
            (name for name, spec in PROVIDERS.items() if os.getenv(spec["key"], "")), "glm"
        )
        spec = PROVIDERS[self.provider]
        prefix = spec["prefix"]
        self.key = os.getenv(spec["key"], "")
        self.base_url = os.getenv(prefix + "_BASE_URL", spec["base_url"])
        self.model = os.getenv(prefix + "_MODEL", spec["model"])
        self.timeout = float(os.getenv(prefix + "_TIMEOUT_SECONDS", "60"))
        self.max_tokens = int(os.getenv(prefix + "_MAX_TOKENS", "4096"))
        self.transport = transport
        url = urlsplit(self.base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("Model base URL must be a plain HTTPS URL")

    @property
    def configured(self):
        return bool(self.key.strip())

    async def json(self, system: str, payload: dict, schema: dict) -> dict:
        if not self.configured:
            raise ModelUnavailable("model_not_configured")
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": system
                    + "\nReturn JSON matching this schema:\n"
                    + json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
        }
        if "reasoner" not in self.model:
            # deepseek-reasoner rejects response_format; its final answer arrives in
            # content while reasoning stays in reasoning_content, so JSON still parses.
            body["response_format"] = {"type": "json_object"}
        if self.provider == "qwen":
            body["enable_thinking"] = False
        elif re.search(r"glm-(4\.[5-9]|5)", self.model):
            # GLM 4.5+/5-series are hybrid reasoning models: hidden thinking burns the
            # shared max_tokens budget and can truncate tool decisions before content.
            body["thinking"] = {"type": "disabled"}
        started = time.monotonic()
        measurement = {
            "provider": self.provider,
            "model": self.model,
            "purpose": payload.get("purpose", "agent_action"),
            "input_characters": sum(len(m["content"]) for m in body["messages"]),
            "usage_reported": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    self.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.key},
                    json=body,
                )
                response.raise_for_status()
            measurement["failure_stage"] = "provider_response_json"
            response_data = response.json()
            usage = response_data.get("usage") or {}
            measurement.update(
                {
                    k: usage[k]
                    for k in ("prompt_tokens", "completion_tokens")
                    if isinstance(usage.get(k), int)
                }
            )
            measurement["usage_reported"] = all(
                k in measurement for k in ("prompt_tokens", "completion_tokens")
            )
            measurement["failure_stage"] = "provider_response_shape"
            choice = response_data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ModelUnavailable("model_truncated_response")
            content = choice["message"]["content"]
            measurement["failure_stage"] = "model_content_json"
            try:
                result, _fenced, recovered = _decode_object(content)
            except json.JSONDecodeError as error:
                measurement["json_error"] = {
                    "message": error.msg,
                    "position": error.pos,
                    "content_length": len(content),
                }
                raise
            if recovered:
                measurement["json_recovered"] = recovered
            if not isinstance(result, dict):
                measurement["json_error"] = {"type": type(result).__name__}
                raise TypeError("Expected JSON object")
            return result
        except httpx.TimeoutException as error:
            detail = transport_diagnostics(error, urlsplit(self.base_url).hostname)
            measurement["transport_error"] = detail
            unavailable = ModelUnavailable("model_timeout")
            unavailable.diagnostics = detail
            log.warning("Model transport error: provider=%s host=%s type=%s causes=%s",
                        self.provider, detail["endpoint_host"], detail["exception_type"], detail["cause_types"])
            raise unavailable from None
        except httpx.HTTPStatusError as error:
            raise ModelUnavailable(f"model_http_{error.response.status_code}") from None
        except httpx.RequestError as error:
            detail = transport_diagnostics(error, urlsplit(self.base_url).hostname)
            measurement["transport_error"] = detail
            unavailable = ModelUnavailable("model_connection_failed")
            unavailable.diagnostics = detail
            log.warning("Model transport error: provider=%s host=%s type=%s causes=%s",
                        self.provider, detail["endpoint_host"], detail["exception_type"], detail["cause_types"])
            raise unavailable from None
        except (ValueError, KeyError, IndexError, TypeError) as error:
            measurement.setdefault("json_error", {"type": type(error).__name__})
            raise ModelUnavailable("model_invalid_json") from None
        finally:
            measurement["seconds"] = round(time.monotonic() - started, 3)
            sink = model_usage.get()
            if sink is not None:
                sink.append(measurement)
