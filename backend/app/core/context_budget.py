"""上下文预算管理模块

负责总计上下文字符预算检查与裁剪，防止超出 LLM 上下文窗口。
裁剪优先级：固定开销(不可裁) > 当前问题(不可裁) > 历史消息(先裁旧的) > 知识库上下文(从末尾裁)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from core.agent_builder import (
    ASSISTANT_IDENTITY_PROMPT,
    DEEP_SYSTEM_PROMPT,
    GENERAL_SYSTEM_TEMPLATE,
    KB_SYSTEM_TEMPLATE,
)
from core.skill_loader import load_skill_files

logger = logging.getLogger("app.core.context_budget")


# ── 固定开销缓存 ────────────────────────────────────────────
_fixed_cost_cache: Optional[dict] = None


def _get_skills_text() -> str:
    skills = load_skill_files()
    return "\n".join(v.get("content", "") for v in skills.values())


def _get_cached_skills_chars() -> int:
    global _fixed_cost_cache
    if _fixed_cost_cache is None or "skills_chars" not in _fixed_cost_cache:
        if _fixed_cost_cache is None:
            _fixed_cost_cache = {}
        _fixed_cost_cache["skills_chars"] = len(_get_skills_text())
    return _fixed_cost_cache["skills_chars"]


def _get_cached_template_chars(mode: str) -> int:
    global _fixed_cost_cache
    key = f"template_{mode}"
    if _fixed_cost_cache is None or key not in _fixed_cost_cache:
        if _fixed_cost_cache is None:
            _fixed_cost_cache = {}
        if mode == "deep":
            template = DEEP_SYSTEM_PROMPT
        elif mode in ("default", "kb"):
            template = KB_SYSTEM_TEMPLATE if mode == "kb" else GENERAL_SYSTEM_TEMPLATE
        else:
            template = GENERAL_SYSTEM_TEMPLATE
        _fixed_cost_cache[key] = len(ASSISTANT_IDENTITY_PROMPT) + len(template)
    return _fixed_cost_cache[key]


def _get_fixed_chars(mode: str) -> int:
    """估算固定开销字符数：system prompt + skills"""
    return _get_cached_template_chars(mode) + _get_cached_skills_chars()


def estimate_tokens(text: str) -> int:
    """基于字符类型估算 token 数（供参考，不参与预算计算）"""
    cjk = 0
    other = 0
    for ch in text:
        cp = ord(ch)
        if ch.isspace():
            continue
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
        ):
            cjk += 1
        else:
            other += 1
    return int(cjk / 1.5 + other / 3.5)


# ── 预算结果 ────────────────────────────────────────────────

@dataclass
class BudgetResult:
    context: str
    history: list
    char_budget: int
    char_used: int
    trimmed: bool
    trimmed_history_rounds: int = 0
    trimmed_context_chars: int = 0


# ── 预算检查主函数 ──────────────────────────────────────────

def apply_context_budget(
    mode: str,
    context: str,
    history_messages: list,
    user_question: str,
    max_chars: int,
) -> BudgetResult:
    """应用上下文预算检查与裁剪。

    裁剪优先级（从低到高）:
      知识库上下文末尾 < 历史消息（旧的先裁） < 当前问题（不可裁） < 固定开销（不可裁）

    参数:
        mode: "deep" | "kb" | "default"
        context: 合并后的知识库上下文字符串
        history_messages: LangChain 消息列表 (HumanMessage | AIMessage)
        user_question: 当前用户问题文本
        max_chars: 预算上限（字符数），<=0 表示不限制

    返回:
        BudgetResult: 裁剪后的结果
    """
    if max_chars <= 0:
        return BudgetResult(
            context=context,
            history=list(history_messages),
            char_budget=0,
            char_used=0,
            trimmed=False,
        )

    # 确定 mode 用于固定开销计算
    budget_mode = "kb" if (mode == "default" and context) else mode

    fixed_chars = _get_fixed_chars(budget_mode)
    mandatory_chars = fixed_chars + len(user_question)

    if mandatory_chars >= max_chars:
        logger.warning(
            "固定开销(%d) + 用户问题(%d) = %d ≥ 预算(%d)，清空可变上下文",
            fixed_chars, len(user_question), mandatory_chars, max_chars,
        )
        return BudgetResult(
            context="",
            history=[],
            char_budget=max_chars,
            char_used=mandatory_chars,
            trimmed=True,
            trimmed_history_rounds=len(history_messages) // 2,
            trimmed_context_chars=len(context),
        )

    budget = max_chars - mandatory_chars
    context_chars = len(context)
    history_chars = sum(len(m.content) for m in history_messages)
    if context_chars + history_chars <= budget:
        return BudgetResult(
            context=context,
            history=list(history_messages),
            char_budget=max_chars,
            char_used=mandatory_chars + context_chars + history_chars,
            trimmed=False,
        )

    # ── 超预算，开始裁剪 ──
    trimmed_history = list(history_messages)
    trimmed_history_rounds = 0

    # Step 1: 从旧到新裁剪历史（保持问答配对）
    while trimmed_history:
        if len(context) + sum(len(m.content) for m in trimmed_history) <= budget:
            break
        if len(trimmed_history) >= 2:
            trimmed_history = trimmed_history[2:]
            trimmed_history_rounds += 1
        else:
            trimmed_history = []
            trimmed_history_rounds += 1

    # Step 2: 历史裁完后仍超预算，裁剪知识库上下文（从末尾截断）
    remaining = budget - sum(len(m.content) for m in trimmed_history)
    trimmed_context = context
    trimmed_context_chars = 0

    if len(context) > remaining:
        if remaining > 0:
            truncated = context[:remaining]
            # 尝试在文件分隔符处截断
            last_sep = truncated.rfind("\n\n--- ")
            if last_sep > 0 and last_sep > remaining * 0.7:
                trimmed_context = truncated[:last_sep]
            else:
                trimmed_context = truncated
        else:
            trimmed_context = ""
        trimmed_context_chars = len(context) - len(trimmed_context)

    total_used = mandatory_chars + len(trimmed_context) + sum(len(m.content) for m in trimmed_history)

    logger.info(
        "上下文已裁剪: 历史 %d→%d 轮, 知识库 %d→%d 字符, 总计 %d/%d",
        len(history_messages) // 2,
        len(trimmed_history) // 2,
        context_chars,
        len(trimmed_context),
        total_used,
        max_chars,
    )

    return BudgetResult(
        context=trimmed_context,
        history=trimmed_history,
        char_budget=max_chars,
        char_used=total_used,
        trimmed=True,
        trimmed_history_rounds=trimmed_history_rounds,
        trimmed_context_chars=trimmed_context_chars,
    )
