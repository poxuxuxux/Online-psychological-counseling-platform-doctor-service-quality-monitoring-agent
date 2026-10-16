import json

import httpx
import pytest

from app.infrastructure.llm.qwen import ModelCallError, QwenConfig, QwenProvider


async def test_qwen_request_and_complete_response():
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "qwen3.5-plus"
        assert body["enable_thinking"] is False
        assert body["stream"] is False
        assert request.url.path == "/compatible-mode/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret-fixture"
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "OK"}}]}
        )

    provider = QwenProvider(QwenConfig("secret-fixture"), httpx.MockTransport(handler))
    assert await provider.complete("system", "synthetic") == "OK"
    assert "secret-fixture" not in repr(provider.config)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
async def test_provider_errors_never_expose_body(status):
    provider = QwenProvider(
        QwenConfig("secret-fixture"),
        httpx.MockTransport(lambda request: httpx.Response(status, text="SECRET PROVIDER BODY")),
    )
    with pytest.raises(ModelCallError) as error:
        await provider.complete("system", "private")
    assert str(error.value) == f"model_http_{status}"


@pytest.mark.parametrize(
    "body,code",
    [
        ({"choices": []}, "model_invalid_response"),
        (
            {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]},
            "model_incomplete_response",
        ),
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            "model_empty_response",
        ),
    ],
)
async def test_invalid_or_truncated_output_is_not_success(body, code):
    provider = QwenProvider(
        QwenConfig("fixture"), httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    with pytest.raises(ModelCallError, match=code):
        await provider.complete("system", "synthetic")


async def test_timeout_is_safe():
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE", request=request)

    provider = QwenProvider(QwenConfig("fixture"), httpx.MockTransport(handler))
    with pytest.raises(ModelCallError, match="^model_timeout$"):
        await provider.complete("system", "synthetic")


def test_configuration_validation(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        QwenConfig.from_env()
    with pytest.raises(ValueError, match="HTTPS"):
        QwenConfig("fixture", base_url="http://localhost")


async def test_native_json_mode_is_explicit_and_does_not_change_plain_smoke():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    provider = QwenProvider(QwenConfig("fixture"), httpx.MockTransport(handler))
    await provider.complete_json("Return JSON", "synthetic")
    await provider.complete("Return OK", "synthetic")
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["enable_thinking"] is False
    assert "response_format" not in bodies[1]
