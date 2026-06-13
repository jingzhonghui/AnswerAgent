"""DeepAgents 知识库工具封装

提供受控的知识库访问工具，所有文件操作限制在 KNOWLEDGE_PATH 内。
底层复用 kb_router.py 和 file_loader.py 的现有逻辑。

工具清单:
- build_knowledge_search_tool(kb_context) → Tool
  迁移自 chain_builder，在预加载上下文中按关键词搜索（兼容旧 deep 模式）
- create_list_kb_tool() → Tool
  列出所有可用的知识库名称
- create_search_kb_tool() → Tool
  在指定知识库中按关键词搜索文件内容
- create_read_kb_file_tool() → Tool
  读取知识库中指定文件的完整内容

安全:
- 所有路径操作通过 file_loader._safe_resolve_in_kb 校验
- 单文件读取有字符上限
- 不开放写入、删除、执行等操作
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from langchain_core.tools import tool

from core.config import settings
from core.file_loader import (
    _safe_resolve_in_kb,
    _TEXT_EXTENSIONS,
    _SINGLE_FILE_CHAR_LIMIT,
    PathSecurityError,
)

logger = logging.getLogger(__name__)


# ============================================================
# 工具 1：知识库搜索（预加载上下文版本，兼容旧链）
# ============================================================

def build_knowledge_search_tool(kb_context: str):
    """构建知识库搜索工具（供旧 AgentExecutor 链使用）

    在预加载的知识库上下文中按关键词搜索。
    此工具依赖外部预先加载好的 kb_context，适合 AgentExecutor 模式。

    Args:
        kb_context: 所有知识库文件的合并内容

    Returns:
        Tool: LangChain StructuredTool 实例
    """
    @tool
    def knowledge_search(query: str) -> str:
        """从本地知识库文件中搜索与 query 相关的信息。

        在回答用户问题前，调用此工具来获取知识库中的相关信息。
        query 应该是你要查找的关键词或问题描述。
        """
        if not kb_context.strip():
            return "（知识库未命中或无可用文件）"
        lines = kb_context.splitlines()
        keywords = query.lower().split()
        matched = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords if kw):
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                snippet = "\n".join(lines[start:end])
                matched.append(f"...[行 {start + 1}-{end}]\n{snippet}")
        result = "\n\n".join(matched[:15])
        if not result:
            return f"未找到与 '{query}' 直接相关的内容。\n\n知识库文件概览:\n{lines[:50]}"
        return result

    return knowledge_search


# ============================================================
# 工具 2：列出知识库
# ============================================================

def create_list_kb_tool(knowledge_root: Optional[Path] = None) -> tool:
    """创建"列出所有知识库"工具

    Args:
        knowledge_root: 知识库根目录，默认使用 settings.get_knowledge_path()

    Returns:
        Tool: 可传入 DeepAgents create_deep_agent(tools=[...])
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()

    @tool
    def list_knowledge_bases() -> str:
        """列出所有可用的知识库名称。

        返回知识库名称列表，每个知识库包含相关文档和源码。
        调用其他知识库工具时需要提供知识库名称（kb_name）。
        """
        if not root.exists() or not root.is_dir():
            return "知识库目录不存在"

        kbs: List[str] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith("."):
                continue
            # 统计文件数
            try:
                file_count = sum(
                    1 for _ in child.rglob("*")
                    if _.is_file() and _.suffix.lower() in _TEXT_EXTENSIONS
                )
            except (OSError, PermissionError):
                file_count = 0
            kbs.append(f"- {name}（{file_count} 个文件）")

        if not kbs:
            return "（无可用知识库）"
        return "\n".join(kbs)

    return list_knowledge_bases


# ============================================================
# 工具 3：在知识库中搜索文件
# ============================================================

def create_search_kb_tool(knowledge_root: Optional[Path] = None) -> tool:
    """创建"在知识库中搜索文件"工具

    对指定知识库的所有文件做关键词匹配，返回相关文件及内容片段。

    Args:
        knowledge_root: 知识库根目录，默认使用 settings.get_knowledge_path()

    Returns:
        Tool: 可传入 DeepAgents create_deep_agent(tools=[...])
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()

    @tool
    def search_kb_files(kb_name: str, query: str) -> str:
        """在指定知识库中搜索与 query 相关的文件内容。

        Args:
            kb_name: 知识库名称（从 list_knowledge_bases 获取）
            query: 搜索关键词或问题描述

        Returns:
            匹配的文件路径和内容片段
        """
        # 路径安全校验
        try:
            kb_root = _safe_resolve_in_kb(root, root / kb_name)
        except PathSecurityError:
            return f"错误：知识库名称无效 - {kb_name}"

        if not kb_root.is_dir():
            return f"知识库 '{kb_name}' 不存在"

        # 扫描知识库内文件
        keywords = query.lower().split()
        if not keywords:
            return "请提供更具体的搜索关键词"

        results: List[str] = []
        file_count = 0

        for file_path in kb_root.rglob("*"):
            if file_count >= 100:  # 最多扫描 100 个文件
                break
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            # 跳过隐藏目录
            try:
                rel = file_path.relative_to(kb_root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue
            # 跳过索引文件自身
            if rel.as_posix() in ("索引.md", "index.md"):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            file_count += 1
            lines = content.splitlines()
            matched_lines: List[str] = []

            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(kw in line_lower for kw in keywords):
                    start = max(0, i - 1)
                    end = min(len(lines), i + 3)
                    snippet = "\n".join(
                        f"  {j + 1}| {lines[j]}"
                        for j in range(start, end)
                    )
                    matched_lines.append(snippet)
                    if len(matched_lines) >= 3:  # 每文件最多 3 处匹配
                        break

            if matched_lines:
                results.append(
                    f"### {rel.as_posix()}\n"
                    + "\n---\n".join(matched_lines)
                )

        if not results:
            return f"在知识库 '{kb_name}' 中未找到与 '{query}' 相关的内容。\n"
            f"提示：尝试使用 list_knowledge_bases 查看可用知识库，"
            f"或使用更通用的搜索词。"

        return f"在 '{kb_name}' 中找到 {len(results)} 个相关文件：\n\n" + "\n\n".join(results[:10])

    return search_kb_files


# ============================================================
# 工具 4：读取知识库文件
# ============================================================

def create_read_kb_file_tool(knowledge_root: Optional[Path] = None) -> tool:
    """创建"读取知识库文件"工具

    安全读取知识库中指定文件的内容，带路径穿越校验和字符上限。

    Args:
        knowledge_root: 知识库根目录，默认使用 settings.get_knowledge_path()

    Returns:
        Tool: 可传入 DeepAgents create_deep_agent(tools=[...])
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()

    @tool
    def read_kb_file(kb_name: str, file_path: str) -> str:
        """读取知识库中指定文件的完整内容。

        Args:
            kb_name: 知识库名称
            file_path: 文件相对路径（从 search_kb_files 返回的结果中获取）

        Returns:
            文件的文本内容（内容过长时可能被截断）
        """
        # 路径安全校验
        try:
            kb_root = _safe_resolve_in_kb(root, root / kb_name)
        except PathSecurityError:
            return f"错误：知识库名称无效 - {kb_name}"

        if not kb_root.is_dir():
            return f"知识库 '{kb_name}' 不存在"

        # 清理路径
        clean_path = file_path.replace("\\", "/").strip().lstrip("./")
        try:
            abs_path = _safe_resolve_in_kb(kb_root, kb_root / clean_path)
        except PathSecurityError:
            return f"错误：文件路径无效或试图访问知识库外部 - {clean_path}"

        if not abs_path.exists() or not abs_path.is_file():
            return f"文件不存在: {clean_path}"

        try:
            text = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = abs_path.read_text(encoding="gbk")
            except (OSError, UnicodeDecodeError):
                return f"错误：无法读取文件 {clean_path}（编码不兼容）"
        except OSError as e:
            return f"错误：读取文件失败 - {e}"

        if len(text) > _SINGLE_FILE_CHAR_LIMIT:
            text = text[:_SINGLE_FILE_CHAR_LIMIT]
            truncated = True
        else:
            truncated = False

        header = f"--- {kb_name}/{clean_path}"
        if truncated:
            header += " (内容已截断)"
        return f"{header}\n{text}"

    return read_kb_file


# ============================================================
# 工具集工厂
# ============================================================

def create_all_kb_tools(knowledge_root: Optional[Path] = None) -> list:
    """创建全套知识库工具（供 DeepAgents deep 模式使用）

    不含 build_knowledge_search_tool（那是给旧 AgentExecutor 用的）。

    Args:
        knowledge_root: 知识库根目录

    Returns:
        list[BaseTool]: 三个知识库工具
    """
    return [
        create_list_kb_tool(knowledge_root),
        create_search_kb_tool(knowledge_root),
        create_read_kb_file_tool(knowledge_root),
    ]