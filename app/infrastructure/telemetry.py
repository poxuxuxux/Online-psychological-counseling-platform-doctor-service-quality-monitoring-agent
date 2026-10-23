# 环节：基础设施适配层；用途：封装模型、数据库或用量遥测等外部能力。
"""Request-scoped usage accounting; no prompts, dialogue or secrets in telemetry."""

from contextvars import ContextVar

model_usage = ContextVar("evaluation_model_usage", default=None)


def usage_summary(records):
    json_errors = [
        {
            "provider": record.get("provider"),
            "model": record.get("model"),
            "stage": record.get("failure_stage"),
            **record["json_error"],
        }
        for record in records
        if isinstance(record.get("json_error"), dict)
    ]
    return {
        "requests": len(records),
        "input_characters": sum(r["input_characters"] for r in records),
        "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in records),
        "completion_tokens": sum(r.get("completion_tokens", 0) for r in records),
        "usage_reported_requests": sum(r.get("usage_reported", False) for r in records),
        "json_errors": json_errors,
    }
