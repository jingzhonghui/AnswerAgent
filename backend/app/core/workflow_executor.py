"""工作流执行模块

按任务表逐一执行，使用 DeepAgent + kb-generator skill 生成知识库文件。
Agent 通过 source_tools 选择性读取源文件，而非一次性倾倒全部内容。
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_factory import create_chat_llm
from core.skill_loader import load_skill_files, get_skill_sources
from core.source_tools import create_source_tools
from models.schemas import AnalysisTask

logger = logging.getLogger(__name__)

EXECUTOR_SYSTEM_PROMPT = """你是一个知识库文件生成引擎。你的输出会直接被保存为最终的 Markdown 文件。

## 核心规则

1. **你的回答就是文件内容本身**。第一行必须是 `# 标题`，不要有任何前置文字。
2. 禁止输出引导语，包括但不限于：
   - "以下是为您生成的..."、"Here is the documentation..."
   - "知识库文件 xxx 已生成，涵盖了以下内容：..."
   - "我会生成..."、"This file would contain..."
3. 禁止输出描述性语言代替实际内容。
4. 不要用 ```markdown 代码块包裹 — 输出纯 Markdown 文本。
5. 输出完成后不要加总结或结尾语。

## 可用工具

- **list_source_files**: 列出源码目录的文件结构
- **read_source_file**: 读取指定文件的完整或部分内容
- **search_source_files**: 在源码中搜索关键词或代码模式

## 工作方式

1. 理解任务描述和目标文件名，确定要生成什么类型的文档
2. 使用 list_source_files 了解目录结构
3. 使用 search_source_files 定位相关文件
4. 使用 read_source_file 深入阅读关键文件
5. 对照 kb-generator 技能中对应文件类型的模板，生成完整文档
6. 直接输出 Markdown 内容（不要代码块包裹）

## 质量标准

- 读者仅阅读这份文档就能理解相关设计，不需要翻阅源码
- 所有代码示例和设计描述来自你实际读取的源文件
- 代码示例完整可用，配置示例无遗漏
- 中文为主，技术术语保留英文原文
"""

# 输出清理正则
_PREAMBLE_PATTERNS = [
    re.compile(r'^[\s\S]*?(?=^#{1,3}\s)', re.MULTILINE),  # 第一个标题之前的所有内容
    re.compile(r'^```(?:markdown)?\s*\n|\n```\s*$', re.MULTILINE),  # 代码块包裹
]
# 引导语关键词
_PREAMBLE_KEYWORDS = [
    "以下是为您生成的", "Here is the", "知识库文件", "已生成",
    "我会生成", "This file would contain", "The file would",
]


def _clean_output(content: str) -> str:
    """清理 LLM 输出，剥离引导语和代码块包裹"""
    content = content.strip()

    # 尝试从第一个 # 标题开始
    for pattern in _PREAMBLE_PATTERNS:
        m = pattern.search(content)
        if m and m.start() > 0:
            content = content[m.start():]

    # 如果内容以引导语开头，尝试找到第一个标题
    first_heading = re.search(r'^#{1,3}\s', content, re.MULTILINE)
    if first_heading and first_heading.start() > 0:
        # 检查开头是否包含引导语关键词
        prefix = content[:first_heading.start()].strip()
        if any(kw in prefix for kw in _PREAMBLE_KEYWORDS):
            content = content[first_heading.start():]

    return content.strip()


def _validate_output(content: str, task_id: str) -> None:
    """验证输出质量，不合格时记录警告"""
    if len(content) < 200:
        logger.warning(f"任务 [{task_id}] 输出内容过短 ({len(content)} 字符)，可能不完整")
    if not re.search(r'^#{1,3}\s', content):
        logger.warning(f"任务 [{task_id}] 输出内容未以标题开头")
    if not re.search(r'^##\s', content, re.MULTILINE):
        logger.warning(f"任务 [{task_id}] 输出内容缺少二级标题")


async def execute_single_task(
    task: AnalysisTask,
    source_dir: Path,
    output_dir: Path,
    repo_type: str,
    completed_context: dict,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """执行单个任务，生成一个知识库文件

    Args:
        task: 任务描述
        source_dir: 源文件目录
        output_dir: 输出目录
        repo_type: 仓库类型 ("code" 或 "doc")
        completed_context: 已完成任务生成的文件内容 {task_id: content}
        log_callback: 日志回调

    Returns:
        str: 生成的文件内容
    """
    msg = f"开始执行任务 [{task.id}]: {task.description} → {task.target_file}"
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    # 构建文件目录摘要（仅路径和大小，不含内容）
    catalog_lines = ["## 源码文件目录", ""]
    try:
        for entry in sorted(source_dir.rglob("*")):
            if not entry.is_file():
                continue
            parts = set(entry.relative_to(source_dir).parts)
            if parts & {".git", "node_modules", "__pycache__", ".venv", "venv",
                        ".idea", ".vscode", "dist", "build", "target"}:
                continue
            rel = entry.relative_to(source_dir).as_posix()
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            catalog_lines.append(f"- {rel} ({size / 1024:.1f}KB)")
    except Exception:
        catalog_lines.append("(无法列出目录)")

    file_catalog = "\n".join(catalog_lines[:200])  # 限制目录条目数

    # 构建已生成文件的上下文
    dep_context = ""
    if task.dependencies:
        dep_context = "\n## 已生成的文件（依赖参考）\n\n"
        for dep_id in task.dependencies:
            if dep_id in completed_context:
                content = completed_context[dep_id]
                dep_context += f"### 依赖文件: {dep_id}\n{content[:2000]}\n\n"
                if len(content) > 2000:
                    dep_context += "...(内容已截断)\n\n"

    # 构建用户消息
    user_message = f"""## 仓库类型
{repo_type}

## 任务描述
{task.description}

## 目标文件
{task.target_file}

{file_catalog}

{dep_context}

## 指令
请使用提供的工具（list_source_files、search_source_files、read_source_file）探索源文件，
按照 kb-generator 技能的规范生成 `{task.target_file}` 的完整内容。

生成的文档质量要求：读者只需要阅读这份文档就能理解相关设计，不需要再翻阅源码。"""

    # 创建 Agent（带源码探索工具）
    llm = create_chat_llm(streaming=False, temperature=0.2)
    source_tools = create_source_tools(source_dir)
    agent = create_deep_agent(
        model=llm,
        system_prompt=EXECUTOR_SYSTEM_PROMPT,
        tools=source_tools,
        middleware=[],
        skills=get_skill_sources(),
    )

    # 加载 skill 文件
    skill_files = load_skill_files()

    payload = {
        "messages": [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ],
    }
    if skill_files:
        payload["files"] = skill_files

    if log_callback:
        log_callback(f"任务 [{task.id}] 正在调用 LLM 生成内容...")
    response = await agent.ainvoke(payload)

    # 提取 AI 生成的最终内容
    output_messages = response.get("messages", [])
    content = ""

    # 调试：记录所有消息类型
    msg_types = []
    for msg in output_messages:
        t = getattr(msg, "type", None) or msg.__class__.__name__
        c = getattr(msg, "content", None)
        c_len = len(str(c)) if c else 0
        msg_types.append(f"{t}({c_len}chars)")

    if log_callback:
        log_callback(f"任务 [{task.id}] 收到 {len(output_messages)} 条消息: {', '.join(msg_types)}")

    for msg in reversed(output_messages):
        msg_type = getattr(msg, "type", None)
        # AIMessage 的 type 可能是 "ai" 或 "AIMessage"
        if msg_type in ("ai", "AIMessage") or (
            msg_type is None and hasattr(msg, "__class__") and "AI" in msg.__class__.__name__
        ):
            raw = getattr(msg, "content", None)
            if raw:
                if isinstance(raw, str):
                    content = raw
                elif isinstance(raw, list):
                    # 新版 LangChain content 可能是 list[dict]
                    parts = []
                    for item in raw:
                        if isinstance(item, dict) and "text" in item:
                            parts.append(item["text"])
                        elif isinstance(item, str):
                            parts.append(item)
                    content = "".join(parts)
                if content.strip():
                    break

    if not content:
        raise ValueError(f"任务 [{task.id}] 未生成任何内容")

    # 清理输出
    content = _clean_output(content)
    _validate_output(content, task.id)

    if log_callback:
        log_callback(f"任务 [{task.id}] 生成内容 {len(content)} 字符")

    # 原子写入文件
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / task.target_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, output_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    msg = f"任务 [{task.id}] 完成: {output_path}"
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    return content


async def execute_tasks(
    task_list: List[AnalysisTask],
    source_dir: Path,
    output_dir: Path,
    repo_type: str,
    completed_task_ids: List[str],
    log_callback: Optional[Callable[[str], None]] = None,
    save_checkpoint: Optional[Callable[[List[str]], Awaitable[None]]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """按依赖顺序执行所有任务

    Returns:
        List[str]: 所有已完成的任务 ID 列表
    """
    completed = set(completed_task_ids)
    completed_context = {}  # task_id -> content
    pending = [t for t in task_list if t.id not in completed]
    all_completed = list(completed_task_ids)

    while pending:
        # 找可执行的任务（依赖都已满足）
        ready = [
            t for t in pending
            if all(dep in completed for dep in t.dependencies)
        ]
        if not ready:
            # 检查是否有循环依赖
            remaining_ids = {t.id for t in pending}
            stuck = True
            for t in pending:
                if all(dep in completed for dep in t.dependencies):
                    stuck = False
                    break
            if stuck:
                raise RuntimeError(
                    f"任务存在循环依赖或无法满足的依赖: {remaining_ids}"
                )
            break

        task = ready[0]
        pending.remove(task)

        # 检查取消
        if is_cancelled and is_cancelled():
            if log_callback:
                log_callback("工作流已取消")
            return all_completed

        content = await execute_single_task(
            task, source_dir, output_dir, repo_type,
            completed_context, log_callback,
        )
        completed_context[task.id] = content
        completed.add(task.id)
        all_completed.append(task.id)

        if save_checkpoint:
            await save_checkpoint(all_completed)

    return all_completed


def generate_index_file(output_dir: Path, task_list: List[AnalysisTask], repo_type: str = "code") -> None:
    """生成知识库索引文件

    CODE 仓库按架构层次组织，DOC 仓库按多级分类组织。
    """
    if repo_type == "code":
        lines = _generate_code_index(task_list)
    else:
        lines = _generate_doc_index(task_list)

    index_path = output_dir / "索引.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"索引文件已生成: {index_path}")


def _generate_code_index(task_list: List[AnalysisTask]) -> List[str]:
    """生成代码仓库的架构层次索引"""
    # 按文件名模式分类
    overview_tasks = []
    arch_tasks = []
    module_tasks = []
    dev_tasks = []
    other_tasks = []

    for t in task_list:
        fn = t.target_file.lower()
        if fn in ("索引.md", "index.md"):
            continue
        if any(kw in fn for kw in ("overview", "readme", "简介", "概述", "概览")):
            overview_tasks.append(t)
        elif any(kw in fn for kw in ("arch", "architecture", "架构", "设计", "design")):
            arch_tasks.append(t)
        elif any(kw in fn for kw in ("api", "接口", "参考", "reference")):
            module_tasks.append(t)
        elif any(kw in fn for kw in ("setup", "install", "deploy", "开发", "搭建", "部署", "环境")):
            dev_tasks.append(t)
        else:
            module_tasks.append(t)  # 默认归入模块

    lines = [
        "# 知识库索引",
        "",
        "本知识库由 AnswerAgent 知识库生成工作流自动生成。",
        "",
    ]

    if overview_tasks:
        lines.append("## 概述")
        lines.append("")
        for t in overview_tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    if arch_tasks:
        lines.append("## 架构设计")
        lines.append("")
        for t in arch_tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    if module_tasks:
        lines.append("## 模块设计")
        lines.append("")
        for t in module_tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    if dev_tasks:
        lines.append("## 开发指南")
        lines.append("")
        for t in dev_tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    if other_tasks:
        lines.append("## 其他")
        lines.append("")
        for t in other_tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    return lines


def _generate_doc_index(task_list: List[AnalysisTask]) -> List[str]:
    """生成文档仓库的多级分类索引"""
    # 按目录分组
    groups: dict = {}
    for t in task_list:
        fn = t.target_file
        if fn in ("索引.md", "index.md"):
            continue
        parts = fn.rsplit("/", 1)
        if len(parts) == 2:
            group = parts[0]
        else:
            group = "其他"

        if group not in groups:
            groups[group] = []
        groups[group].append(t)

    lines = [
        "# 知识库索引",
        "",
        "本知识库由 AnswerAgent 知识库生成工作流自动生成。",
        "",
    ]

    for group_name, tasks in sorted(groups.items()):
        display_name = group_name.replace("_", " ").replace("-", " ")
        lines.append(f"## {display_name}")
        lines.append("")
        for t in tasks:
            lines.append(f"- [{t.target_file}]({t.target_file}) — {t.description}")
        lines.append("")

    return lines