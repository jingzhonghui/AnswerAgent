"""源码探索工具

为知识库生成 executor agent 提供源码探索能力，让 agent 可以
选择性读取源文件，而非一次性倾倒全部内容。

工具清单:
- create_list_source_tool(source_dir) → Tool
  列出源码目录的文件结构
- create_read_source_tool(source_dir) → Tool
  读取指定文件的完整或部分内容
- create_search_source_tool(source_dir) → Tool
  在源码中按关键词搜索
- create_source_tools(source_dir) → list
  工厂函数，返回全部三个工具

安全:
- 所有路径操作限制在 source_dir 内
- 跳过隐藏目录和二进制文件
- 单文件读取有字符上限
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Set

from langchain_core.tools import tool

from core.file_loader import _TEXT_EXTENSIONS, _SINGLE_FILE_CHAR_LIMIT

logger = logging.getLogger(__name__)

# 搜索工具限制
_MAX_SEARCH_FILES = 100
_MAX_SEARCH_MATCHES = 15
_MAX_LIST_ENTRIES = 200
_CONTEXT_LINES = 3


# ============================================================
# 路径安全
# ============================================================

def _safe_resolve_in_source(source_root: Path, target: Path) -> Path:
    """resolve target 并校验其落在 source_root 内"""
    resolved = target.resolve()
    try:
        resolved.relative_to(source_root)
    except ValueError:
        raise ValueError(f"路径越界: {target} -> {resolved}")
    return resolved


# ============================================================
# 工具 1：列出源码目录结构
# ============================================================

def create_list_source_tool(source_dir: Path) -> tool:
    """创建"列出源码文件结构"工具"""
    root = source_dir.resolve()

    @tool
    def list_source_files(subdirectory: str = "") -> str:
        """列出源码目录的文件结构。

        Args:
            subdirectory: 子目录路径（相对于源码根目录），默认为空表示根目录

        Returns:
            目录树结构，每行格式：路径（大小）
        """
        try:
            if subdirectory:
                clean = subdirectory.replace("\\", "/").strip().lstrip("./")
                target = _safe_resolve_in_source(root, root / clean)
            else:
                target = root
        except ValueError as e:
            return f"错误：{e}"

        if not target.exists() or not target.is_dir():
            return f"目录不存在: {subdirectory or '.'}"

        entries: List[str] = []
        count = 0
        for entry in sorted(target.iterdir()):
            if count >= _MAX_LIST_ENTRIES:
                entries.append(f"...（共 {sum(1 for _ in target.iterdir())} 个条目，仅显示前 {_MAX_LIST_ENTRIES}）")
                break
            name = entry.name
            if name.startswith("."):
                continue
            try:
                rel = entry.relative_to(root).as_posix()
            except ValueError:
                continue
            if entry.is_dir():
                entries.append(f"📁 {rel}/")
            else:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / 1024 / 1024:.1f}MB"
                entries.append(f"📄 {rel} ({size_str})")
            count += 1

        if not entries:
            return f"目录为空: {subdirectory or '.'}"
        return "\n".join(entries)

    return list_source_files


# ============================================================
# 工具 2：读取源码文件
# ============================================================

def create_read_source_tool(source_dir: Path) -> tool:
    """创建"读取源码文件"工具"""
    root = source_dir.resolve()

    @tool
    def read_source_file(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
        """读取源码文件的内容。可指定行范围来读取大文件的部分内容。

        Args:
            file_path: 文件相对路径（从 list_source_files 获取）
            start_line: 起始行号（从 1 开始，0 表示从头开始）
            end_line: 结束行号（包含，0 表示到文件末尾）

        Returns:
            文件内容（可能被截断）
        """
        clean = file_path.replace("\\", "/").strip().lstrip("./")
        try:
            abs_path = _safe_resolve_in_source(root, root / clean)
        except ValueError as e:
            return f"错误：{e}"

        if not abs_path.exists() or not abs_path.is_file():
            return f"文件不存在: {clean}"

        if abs_path.suffix.lower() not in _TEXT_EXTENSIONS:
            return f"不支持的文件类型: {abs_path.suffix}"

        try:
            text = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = abs_path.read_text(encoding="gbk")
            except (OSError, UnicodeDecodeError):
                return f"错误：无法读取文件 {clean}（编码不兼容）"
        except OSError as e:
            return f"错误：读取文件失败 - {e}"

        lines = text.splitlines()

        # 处理行范围
        if start_line > 0 or end_line > 0:
            start = max(0, start_line - 1) if start_line > 0 else 0
            end = min(len(lines), end_line) if end_line > 0 else len(lines)
            if start >= len(lines):
                return f"错误：起始行 {start_line} 超出文件总行数 {len(lines)}"
            lines = lines[start:end]
            text = "\n".join(lines)

        # 截断
        if len(text) > _SINGLE_FILE_CHAR_LIMIT:
            text = text[:_SINGLE_FILE_CHAR_LIMIT]
            truncated = True
        else:
            truncated = False

        header = f"--- {clean}"
        if start_line > 0 or end_line > 0:
            header += f" (行 {max(1, start_line)}-{end_line if end_line > 0 else len(lines)})"
        if truncated:
            header += " (内容已截断)"
        return f"{header}\n{text}"

    return read_source_file


# ============================================================
# 工具 3：搜索源码文件
# ============================================================

def create_search_source_tool(source_dir: Path) -> tool:
    """创建"搜索源码文件"工具"""
    root = source_dir.resolve()

    @tool
    def search_source_files(query: str, file_pattern: str = "") -> str:
        """在源码文件中搜索关键词。

        Args:
            query: 搜索关键词（支持多个词，空格分隔）
            file_pattern: 文件名过滤（如 \"*.py\" 或 \"*.ts\"），留空搜索所有文本文件

        Returns:
            匹配的文件路径和上下文片段
        """
        keywords = query.lower().split()
        if not keywords:
            return "请提供搜索关键词"

        results: List[str] = []
        file_count = 0

        for file_path in sorted(root.rglob("*")):
            if file_count >= _MAX_SEARCH_FILES:
                break
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            if file_path.name.startswith("."):
                continue

            # 文件名过滤
            if file_pattern:
                if not file_path.match(file_pattern):
                    continue

            try:
                rel = file_path.relative_to(root).as_posix()
            except ValueError:
                continue

            # 跳过隐藏目录中的文件
            if any(part.startswith(".") for part in file_path.relative_to(root).parts):
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
                    start = max(0, i - _CONTEXT_LINES)
                    end = min(len(lines), i + _CONTEXT_LINES + 1)
                    snippet = "\n".join(
                        f"  {j + 1}| {lines[j]}"
                        for j in range(start, end)
                    )
                    matched_lines.append(snippet)
                    if len(matched_lines) >= 3:
                        break

            if matched_lines:
                results.append(
                    f"### {rel}\n"
                    + "\n---\n".join(matched_lines)
                )

            if len(results) >= _MAX_SEARCH_MATCHES:
                break

        if not results:
            hint = f"（文件类型过滤: {file_pattern}）" if file_pattern else ""
            return f"未找到与 '{query}' 相关的内容{hint}"

        return f"找到 {len(results)} 个匹配：\n\n" + "\n\n".join(results)

    return search_source_files


# ============================================================
# 工具集工厂
# ============================================================

def create_source_tools(source_dir: Path) -> list:
    """创建全套源码探索工具

    Args:
        source_dir: 源码根目录

    Returns:
        list: [list_source_files, read_source_file, search_source_files]
    """
    return [
        create_list_source_tool(source_dir),
        create_read_source_tool(source_dir),
        create_search_source_tool(source_dir),
    ]