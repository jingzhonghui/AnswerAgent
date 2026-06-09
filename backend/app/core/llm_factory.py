"""LLM 工厂模块

根据 settings.llm_provider 统一创建 LangChain Chat Model，
供 kb_router、file_loader、chain_builder 共用。

支持两种 provider:
- "openai"   -> ChatOpenAI（也兼容 DeepSeek、通义千问等 OpenAI 兼容 API）
- "anthropic" -> ChatAnthropic

默认模型使用 settings.api_key / base_url / model 和 settings.llm_provider。
深度思考模型（reasoning=True）使用独立的 settings.deep_api_key / deep_base_url / deep_model
和 settings.deep_llm_provider（空则复用默认模型的 provider）。

无 API key 时直接抛出 LLMConfigError，由调用方决定如何处理。
"""
from __future__ import annotations

from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from core.config import settings


class LLMConfigError(Exception):
    """LLM 配置错误（缺 key、provider 非法等）"""
    pass


def create_chat_llm(
    streaming: bool = False,
    temperature: float = 0.2,
    model: Optional[str] = None,
    reasoning: bool = False,
):
    """创建 LangChain Chat Model 实例

    Args:
        streaming: 是否启用流式输出
        temperature: 采样温度
        model: 覆盖默认 model 名称
        reasoning: 是否使用深度思考（推理）模型；为 True 时使用 deep_* 配置

    Returns:
        BaseChatModel: LangChain chat model 实例

    Raises:
        LLMConfigError: provider 不支持或缺少 API key
    """
    if reasoning:
        if not settings.deep_model_enabled:
            raise LLMConfigError("Deep thinking model is disabled via DEEP_MODEL_ENABLED=False")
        provider = (settings.deep_llm_provider or settings.llm_provider or "").lower().strip()
        model_name = model or settings.deep_model or settings.model
        api_key = settings.deep_api_key or settings.api_key
        base_url = settings.deep_base_url or settings.base_url
        temp = settings.deep_temperature
    else:
        provider = (settings.llm_provider or "").lower().strip()
        model_name = model or settings.model
        api_key = settings.api_key
        base_url = settings.base_url
        temp = temperature

    if provider == "openai":
        if not api_key or api_key.startswith("sk-xxx"):
            raise LLMConfigError(
                "API_KEY is not configured for OpenAI provider. "
                "Please set API_KEY (or DEEP_API_KEY for deep mode) in backend/.env"
            )
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            model=model_name,
            temperature=temp,
            streaming=streaming,
        )

    if provider == "anthropic":
        if not api_key or api_key.startswith("sk-ant-xxx"):
            raise LLMConfigError(
                "API_KEY is not configured for Anthropic provider. "
                "Please set API_KEY (or DEEP_API_KEY for deep mode) in backend/.env"
            )
        return ChatAnthropic(
            api_key=api_key,
            base_url=base_url or None,
            model=model_name,
            temperature=temp,
            streaming=streaming,
        )

    raise LLMConfigError(
        f"Unsupported LLM_PROVIDER: {provider!r}. "
        "Expected 'openai' or 'anthropic'."
    )