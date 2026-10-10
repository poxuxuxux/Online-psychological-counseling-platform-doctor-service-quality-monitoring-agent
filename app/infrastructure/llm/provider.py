"""功能：定义语言模型客户端接口；具体 SDK、密钥和重试逻辑由适配器实现。"""

from typing import Protocol


class LLMProvider(Protocol):
    """AgentRunner 依赖此协议而非某家模型 SDK 的具体类。"""

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """返回模型文本结果；结构化输出解析和安全校验由调用层负责。"""
        ...
