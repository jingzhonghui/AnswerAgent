"""知识库路由模块

职责:
- 扫描 KNOWLEDGE_PATH 一级子目录，得到所有可用知识库。
- 给定用户问题，调用 LLM 从候选知识库中多选最相关项。
- 加载每个知识库的 索引.md（若存在）作为路由提示，提高匹配准确率。

安全:
- 仅认可"一级子目录"作为知识库，子目录里的内部结构不暴露给路由层。
- 知识库名禁止以 . 开头、不能包含路径分隔符（这种情况 Path 不会产生但显式校验一遍）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from core.llm_factory import create_chat_llm


# 单个知识库 索引.md 注入路由 prompt 的字符上限，避免大目录撑爆 token
_INDEX_PREVIEW_LIMIT = 2000


class KBRouterError(Exception):
    """知识库路由异常"""
    pass


def list_knowledge_bases(knowledge_root: Optional[Path] = None) -> List[str]:
    """扫描 KNOWLEDGE_PATH 一级子目录

    Args:
        knowledge_root: 可选覆盖根目录（测试用），默认 settings.get_knowledge_path()

    Returns:
        List[str]: 知识库名称列表，按名称字母序排序；目录不存在时返回空列表
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()
    if not root.exists() or not root.is_dir():
        return []

    kbs: List[str] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        # 跳过隐藏目录和路径不安全名称
        if name.startswith(".") or "/" in name or "\\" in name:
            continue
        kbs.append(name)

    kbs.sort()
    return kbs


def _read_index_preview(kb_root: Path) -> str:
    """读取知识库的 索引.md（若存在），截断到字符上限

    Returns:
        str: 索引内容预览，无索引文件返回空字符串
    """
    index_file = kb_root / "索引.md"
    if not index_file.exists() or not index_file.is_file():
        # 兼容英文别名
        index_file = kb_root / "index.md"
        if not index_file.exists() or not index_file.is_file():
            return ""
    try:
        text = index_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if len(text) > _INDEX_PREVIEW_LIMIT:
        text = text[:_INDEX_PREVIEW_LIMIT] + "\n...(truncated)"
    return text


def _build_kb_catalog(kb_names: List[str], knowledge_root: Path) -> str:
    """为 LLM 构造知识库目录描述

    每条形如：
        - 名称：xxx
          描述：(索引.md 预览或"无描述")
    """
    blocks: List[str] = []
    for name in kb_names:
        kb_root = knowledge_root / name
        preview = _read_index_preview(kb_root)
        if preview:
            desc_block = "\n".join("    " + ln for ln in preview.splitlines())
            blocks.append(f"- 名称: {name}\n  描述:\n{desc_block}")
        else:
            blocks.append(f"- 名称: {name}\n  描述: (无 索引.md)")
    return "\n\n".join(blocks)


_ROUTER_SYSTEM_PROMPT = (
    "你是一个知识库路由助手。\n"
    "用户会给出一个问题，以及若干候选知识库及其简要描述。\n"
    "你的任务是从候选知识库中**多选**出与问题最相关的知识库名称。\n"
    "\n"
    "判断规则:\n"
    "1. 如果某知识库的描述明确涉及问题的主题/实体/技术名词，则匹配。\n"
    "2. 不要凭空捏造不存在的知识库名称；必须从候选列表中选择。\n"
    "3. 如果所有候选知识库都与问题无关，返回空数组。\n"
    "4. 严格只返回 JSON，禁止任何额外说明文字。\n"
    "\n"
    '输出格式: {"kb_names": ["名称1", "名称2"]}'
)


def _parse_router_json(raw: str, candidates: List[str]) -> List[str]:
    """从 LLM 响应中解析出 kb_names，并与候选列表交集去重

    容错: 若返回的不是纯 JSON，尝试用正则提取首个 {...} 块。
    """
    text = raw.strip()
    # 去掉可能的 ```json ``` 包裹
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        return []

    names = data.get("kb_names", [])
    if not isinstance(names, list):
        return []

    # 只保留实际存在的候选，按候选列表顺序去重
    candidate_set = set(candidates)
    seen = set()
    result: List[str] = []
    for n in names:
        if not isinstance(n, str):
            continue
        if n in candidate_set and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def route_knowledge_bases(
    question: str,
    knowledge_root: Optional[Path] = None,
) -> List[str]:
    """根据用户问题，路由到匹配的知识库列表

    Args:
        question: 用户问题
        knowledge_root: 可选覆盖根目录（测试用）

    Returns:
        List[str]: 匹配的知识库名称列表，没有候选或没有匹配时返回 []

    Raises:
        LLMConfigError: LLM 配置错误（透传自 llm_factory）
        KBRouterError: 其他路由错误
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()
    candidates = list_knowledge_bases(root)
    if not candidates:
        return []

    catalog = _build_kb_catalog(candidates, root)
    user_prompt = (
        f"候选知识库:\n{catalog}\n\n"
        f"用户问题: {question}\n\n"
        '请返回 JSON: {"kb_names": [...]}'
    )

    llm = create_chat_llm(streaming=False, temperature=0.0)
    try:
        response = llm.invoke([
            SystemMessage(content=_ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as e:  # 网络/鉴权等运行时错误
        raise KBRouterError(f"LLM routing failed: {e}") from e

    raw = response.content if hasattr(response, "content") else str(response)
    if isinstance(raw, list):
        # 某些 provider 返回 content 为 list[dict]
        raw = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )

    return _parse_router_json(raw, candidates)
