"""LLM 工厂模块

根据运行时模型配置统一创建 LangChain Chat Model，
供 kb_router、file_loader、agent_builder 共用。

支持两种 provider:
- "openai"   -> ChatOpenAI（也兼容 DeepSeek、通义千问等 OpenAI 兼容 API）
- "anthropic" -> ChatAnthropic

配置优先级: 数据库 > 环境变量 > 默认值
通过 core.model_config 运行时配置服务读取，管理界面可热更新。
"""
from __future__ import annotations

from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from core import model_config as mc


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
        deep_enabled = mc.get("deep_model_enabled", "true").lower() == "true"
        if not deep_enabled:
            raise LLMConfigError("Deep thinking model is disabled")
        provider = (mc.get("deep_llm_provider") or mc.get("llm_provider") or "").lower().strip()
        model_name = model or mc.get("deep_model") or mc.get("model") or "o1-mini"
        api_key = mc.get("deep_api_key") or mc.get("api_key")
        base_url = mc.get("deep_base_url") or mc.get("base_url")
        try:
            temp = float(mc.get("deep_temperature", "0.1"))
        except ValueError:
            temp = 0.1
    else:
        provider = (mc.get("llm_provider") or "").lower().strip()
        model_name = model or mc.get("model") or "gpt-4o"
        api_key = mc.get("api_key")
        base_url = mc.get("base_url")
        try:
            temp = float(mc.get("temperature", "0.2"))
        except ValueError:
            temp = temperature

    if provider == "openai":
        if not api_key or api_key.startswith("sk-xxx"):
            raise LLMConfigError(
                "API_KEY is not configured for OpenAI provider. "
                "Please set API_KEY (or DEEP_API_KEY for deep mode) in admin panel"
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
                "Please set API_KEY (or DEEP_API_KEY for deep mode) in admin panel"
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