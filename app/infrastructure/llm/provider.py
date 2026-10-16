"""功能：定义语言模型客户端接口；具体 SDK、密钥和重试逻辑由适配器实现。"""

from typing import Protocol


class LLMProvider(Protocol):
    """AgentRunner 依赖此协议而非某家模型 SDK 的具体类。"""

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """返回模型文本结果；结构化输出解析和安全校验由调用层负责。"""
        ...


async def complete_json(provider: LLMProvider, system_prompt: str, user_prompt: str) -> str:
    """Use native JSON output when supported; retain the text protocol for test/adaptor compatibility."""
    method = getattr(provider, "complete_json", None)
    if callable(method):
        return await method(system_prompt, user_prompt)
    return await provider.complete(system_prompt, user_prompt)
