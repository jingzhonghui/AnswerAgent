"""LLM 工厂模块

根据 settings.llm_provider 统一创建 LangChain Chat Model，
供 kb_router、file_loader、chain_builder 共用。

支持:
- openai   -> ChatOpenAI
- anthropic -> ChatAnthropic

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
):
    """创建 LangChain Chat Model 实例

    Args:
        streaming: 是否启用流式输出（M3 调用时设为 True）
        temperature: 采样温度，默认 0.2 以提高路由/选文件的稳定性
        model: 覆盖默认 model 名称

    Returns:
        BaseChatModel: LangChain chat model 实例

    Raises:
        LLMConfigError: provider 不支持或缺少 API key
    """
    provider = (settings.llm_provider or "").lower().strip()

    if provider == "openai":
        api_key = settings.openai_api_key
        if not api_key or api_key.startswith("sk-xxx"):
            raise LLMConfigError(
                "OPENAI_API_KEY is not configured. "
                "Please set it in backend/.env"
            )
        return ChatOpenAI(
            api_key=api_key,
            base_url=settings.openai_base_url or None,
            model=model or settings.openai_model,
            temperature=temperature,
            streaming=streaming,
        )

    if provider == "anthropic":
        api_key = settings.anthropic_api_key
        if not api_key or api_key.startswith("sk-ant-xxx"):
            raise LLMConfigError(
                "ANTHROPIC_API_KEY is not configured. "
                "Please set it in backend/.env"
            )
        return ChatAnthropic(
            api_key=api_key,
            base_url=settings.anthropic_base_url or None,
            model=model or settings.anthropic_model,
            temperature=temperature,
            streaming=streaming,
        )

    raise LLMConfigError(
        f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}. "
        "Expected 'openai' or 'anthropic'."
    )
