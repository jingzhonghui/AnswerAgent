"""工作流分析模块

扫描源文件目录，使用 LLM 生成知识库文件任务表。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_factory import create_chat_llm
from models.schemas import AnalysisTask

logger = logging.getLogger(__name__)

# 文件扫描限制
MAX_SCAN_FILES = 500
MAX_FILE_SIZE_FOR_READ = 500 * 1024  # 500KB
# 扫描时忽略的目录和文件
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", ".next", ".nuxt",
    "target", "vendor", ".cache", ".tox", ".eggs",
}
IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".ttf", ".woff", ".woff2", ".eot",
    ".lock", ".log",
}
TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".scss", ".less",
    ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".sql", ".graphql", ".proto",
    ".xml", ".rss", ".csv",
    ".vue", ".svelte",
    ".env.example", ".gitignore", "Dockerfile", "Makefile",
}


def scan_files(source_dir: Path) -> dict:
    """扫描源目录，返回文件目录结构

    Returns:
        dict: {
            "root_name": str,
            "total_files": int,
            "total_size_mb": float,
            "file_tree": [{"path": str, "size": int, "ext": str}, ...]
        }
    """
    file_tree = []
    total_size = 0
    file_count = 0

    for entry in source_dir.rglob("*"):
        if entry.is_file():
            # 检查忽略目录
            parts = set(entry.relative_to(source_dir).parts)
            if parts & IGNORE_DIRS:
                continue

            suffix = entry.suffix.lower()
            if suffix in IGNORE_EXTENSIONS:
                continue

            file_count += 1
            if file_count > MAX_SCAN_FILES:
                logger.warning(f"文件数超过上限 {MAX_SCAN_FILES}，停止扫描")
                break

            size = entry.stat().st_size
            total_size += size
            rel_path = str(entry.relative_to(source_dir)).replace("\\", "/")
            file_tree.append({
                "path": rel_path,
                "size": size,
                "ext": suffix or "(无扩展名)",
            })

    return {
        "root_name": source_dir.name,
        "total_files": len(file_tree),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "file_tree": sorted(file_tree, key=lambda x: x["path"]),
        "repo_type": _classify_repo_type(file_tree),
    }


def _read_file_content(file_path: Path, max_size: int = MAX_FILE_SIZE_FOR_READ) -> Optional[str]:
    """读取文件内容（限制大小）"""
    try:
        size = file_path.stat().st_size
        if size > max_size:
            return f"(文件过大，已跳过: {size / 1024:.0f}KB)"
        content = file_path.read_text(encoding="utf-8", errors="replace")
        # 截断过长的内容
        if len(content) > 5000:
            return content[:5000] + "\n...(内容已截断)"
        return content
    except Exception:
        return None


def build_file_catalog(source_dir: Path, scan_result: dict) -> str:
    """构建供 LLM 分析的文件目录摘要"""
    repo_type = scan_result.get("repo_type", "doc")
    lines = [
        f"## 项目目录: {scan_result['root_name']}",
        f"文件总数: {scan_result['total_files']}",
        f"总大小: {scan_result['total_size_mb']} MB",
        f"仓库类型: {'代码仓库' if repo_type == 'code' else '文档仓库'}",
        "",
        "### 文件列表",
        "| 路径 | 大小 | 类型 |",
        "|------|------|------|",
    ]

    for f in scan_result["file_tree"]:
        size_kb = f["size"] / 1024
        lines.append(f"| {f['path']} | {size_kb:.1f}KB | {f['ext']} |")

    # 读取关键文件的内容摘要
    lines.append("")
    lines.append("### 关键文件内容摘要")
    key_files = ["README.md", "README", "package.json", "setup.py", "pyproject.toml",
                 "go.mod", "Cargo.toml", "index.md", "索引.md", "CLAUDE.md"]
    for f in scan_result["file_tree"]:
        name = f["path"].split("/")[-1]
        if name in key_files or name.endswith(".md"):
            file_path = source_dir / f["path"]
            content = _read_file_content(file_path)
            if content:
                lines.append(f"\n#### {f['path']}")
                lines.append(f"```\n{content}\n```")

    return "\n".join(lines)


def _extract_json_from_response(text: str) -> Optional[dict]:
    """从 LLM 响应中提取 JSON 对象"""
    # 尝试匹配 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1)

    # 尝试匹配 JSON 对象
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# 仓库类型分类
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt",
    ".scala", ".vue", ".svelte", ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".sql", ".graphql", ".proto",
}
DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc"}


def _classify_repo_type(file_tree: list) -> str:
    """根据文件扩展名统计分类仓库类型

    Returns:
        str: "code" 或 "doc"
    """
    code_count = 0
    doc_count = 0
    for f in file_tree:
        ext = f["ext"]
        if ext in CODE_EXTENSIONS:
            code_count += 1
        elif ext in DOC_EXTENSIONS:
            doc_count += 1
    total = code_count + doc_count
    if total == 0:
        return "doc"
    if code_count / total > 0.5:
        return "code"
    return "doc"


PLANNING_PROMPT = """你是一个知识库构建专家。根据以下项目文件目录和仓库类型，制定知识库文件生成任务表。

## 仓库类型: {repo_type}

### 代码仓库指引
- 分析项目结构，确定核心模块和组件
- 为每个核心模块/组件生成详细设计文档（功能、模块关系、技术栈、核心设计）
- 必须包含顶层概述文档（项目概述、技术栈、目录结构）
- 索引文件按架构层次组织（概述 → 架构 → 模块 → 开发指南）
- 任务之间可以有依赖关系

### 文档仓库指引
- **索引.md 是最重要的文件**，所有内容从索引出发
- 分析现有文件内容，按主题重新组织为多级索引
- 大目录（文件数 > 20）拆分为子索引文件
- 将非 Markdown 格式的文档转换为 Markdown
- 保留原始文件的引用链接

## 任务要求
1. 每个任务对应生成一个知识库文件（Markdown 格式）
2. 任务之间可以有依赖关系（例如 API 文档依赖架构概述）
3. 知识库名称应该简洁有意义，从项目名称推断
4. 必须包含 索引.md 作为知识库入口
5. description 要具体可操作，不要泛泛而谈

## 输出格式
严格按以下 JSON 格式输出（不要包含其他内容）：

```json
{{
  "knowledge_name": "知识库目录名称",
  "tasks": [
    {{
      "id": "t1",
      "description": "涵盖项目背景、核心功能、技术选型理由",
      "target_file": "overview.md",
      "dependencies": []
    }}
  ]
}}
```

## 项目文件目录
"""


async def generate_task_list(source_dir: Path, scan_result: dict, repo_type: str = "code") -> tuple[str, List[AnalysisTask]]:
    """使用 LLM 分析文件目录，生成知识库任务表

    Returns:
        tuple[str, List[AnalysisTask]]: (知识库名称, 任务列表)
    """
    catalog = build_file_catalog(source_dir, scan_result)

    llm = create_chat_llm(streaming=False, temperature=0.2)
    messages = [
        SystemMessage(content=PLANNING_PROMPT.format(repo_type=repo_type)),
        HumanMessage(content=catalog),
    ]

    logger.info("正在调用 LLM 生成知识库任务表...")
    response = await llm.ainvoke(messages)
    response_text = response.content if hasattr(response, "content") else str(response)
    logger.info(f"LLM 分析响应: {response_text[:500]}...")

    data = _extract_json_from_response(response_text)
    if not data:
        raise ValueError(f"无法从 LLM 响应中解析任务表 JSON: {response_text[:500]}")

    knowledge_name = data.get("knowledge_name", scan_result["root_name"])
    # 清理知识库名称
    knowledge_name = re.sub(r"[^\w一-鿿_-]", "_", knowledge_name).strip("_")

    tasks = []
    for item in data.get("tasks", []):
        task = AnalysisTask(
            id=item["id"],
            description=item["description"],
            target_file=item["target_file"],
            dependencies=item.get("dependencies", []),
        )
        tasks.append(task)

    if not tasks:
        raise ValueError("LLM 未生成任何任务")

    logger.info(f"知识库名称: {knowledge_name}, 任务数: {len(tasks)}")
    return knowledge_name, tasks