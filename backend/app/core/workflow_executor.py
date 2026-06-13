"""工作流执行模块

按任务表逐一执行，使用 DeepAgent + kb-generator skill 生成知识库文件。
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_factory import create_chat_llm
from core.skill_loader import load_skill_files, get_skill_sources
from models.schemas import AnalysisTask

logger = logging.getLogger(__name__)

EXECUTOR_SYSTEM_PROMPT = """你是一个知识库文件生成专家。根据提供的源文件内容和任务描述，生成一个高质量的知识库 Markdown 文件。

## 规则
1. 只输出文件内容本身，不要添加额外说明
2. 使用 Markdown 格式，包含适当的标题层级
3. 引用源文件时，使用相对路径
4. 代码示例要完整可用
5. 中文为主，技术术语保留英文
6. 遵守 kb-generator skill 中定义的格式规范

## 输出格式
直接输出 Markdown 文件内容，以一级标题 `# 标题` 开头。
"""


def _read_source_files(
    source_dir: Path,
    file_patterns: Optional[List[str]] = None,
    max_total_size: int = 500 * 1024,
) -> str:
    """读取源文件内容作为上下文

    Args:
        source_dir: 源文件目录
        file_patterns: 可选的文件模式过滤
        max_total_size: 最大总读取大小
    """
    parts = []
    total_size = 0
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv",
                   ".idea", ".vscode", "dist", "build", "target"}
    text_exts = {".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
                 ".json", ".yaml", ".yml", ".toml", ".html", ".css",
                 ".java", ".go", ".rs", ".c", ".cpp", ".h", ".vue",
                 ".sh", ".sql", ".xml", ".ini", ".cfg", ".env.example"}

    for entry in sorted(source_dir.rglob("*")):
        if entry.is_file():
            parts_set = set(entry.relative_to(source_dir).parts)
            if parts_set & ignore_dirs:
                continue
            if entry.suffix.lower() not in text_exts:
                continue

            rel_path = str(entry.relative_to(source_dir)).replace("\\", "/")
            try:
                size = entry.stat().st_size
                if total_size + size > max_total_size:
                    parts.append(f"\n### {rel_path}\n(文件过大，已跳过)\n")
                    continue

                content = entry.read_text(encoding="utf-8", errors="replace")
                if len(content) > 3000:
                    content = content[:3000] + "\n...(内容已截断)"
                parts.append(f"\n### {rel_path}\n```\n{content}\n```\n")
                total_size += size
            except Exception:
                parts.append(f"\n### {rel_path}\n(无法读取)\n")

    return "\n".join(parts)


async def execute_single_task(
    task: AnalysisTask,
    source_dir: Path,
    output_dir: Path,
    completed_context: dict,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """执行单个任务，生成一个知识库文件

    Args:
        task: 任务描述
        source_dir: 源文件目录
        output_dir: 输出目录
        completed_context: 已完成任务生成的文件内容 {task_id: content}
        log_callback: 日志回调

    Returns:
        str: 生成的文件内容
    """
    msg = f"开始执行任务 [{task.id}]: {task.description} → {task.target_file}"
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    # 读取源文件内容
    source_context = _read_source_files(source_dir)

    # 构建已生成文件的上下文
    dep_context = ""
    if task.dependencies:
        dep_context = "\n## 已生成的文件（依赖参考）\n\n"
        for dep_id in task.dependencies:
            if dep_id in completed_context:
                content = completed_context[dep_id]
                dep_context += f"### 文件: {dep_id}\n{content[:2000]}\n\n"
                if len(content) > 2000:
                    dep_context += "...(内容已截断)\n\n"

    # 构建用户消息
    user_message = f"""## 任务描述
{task.description}

## 目标文件
{task.target_file}

## 源文件内容
{source_context}

{dep_context}

请根据以上信息生成知识库文件 `{task.target_file}` 的完整内容。"""

    # 创建 Agent
    llm = create_chat_llm(streaming=False, temperature=0.2)
    agent = create_deep_agent(
        model=llm,
        system_prompt=EXECUTOR_SYSTEM_PROMPT,
        tools=[],
        middleware=[],
        skills=get_skill_sources(),
    )

    # 加载 skill 文件
    skill_files = load_skill_files()

    messages = [
        SystemMessage(content=EXECUTOR_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    payload = {"messages": messages}
    if skill_files:
        payload["files"] = skill_files

    response = await agent.ainvoke(payload)

    # 提取生成的内容
    output_messages = response.get("messages", [])
    content = ""
    for msg in output_messages:
        if hasattr(msg, "content") and msg.content:
            # 取最后一条 AI 消息
            if hasattr(msg, "type") and msg.type == "ai":
                content = msg.content
            elif not hasattr(msg, "type"):
                content = msg.content

    if not content:
        raise ValueError(f"任务 [{task.id}] 未生成任何内容")

    # 清理内容（去掉开头可能的非 Markdown 内容）
    content = content.strip()

    # 写入文件
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / task.target_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 原子写入
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
    completed_task_ids: List[str],
    log_callback: Optional[Callable[[str], None]] = None,
    save_checkpoint: Optional[Callable[[], None]] = None,
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
            task, source_dir, output_dir, completed_context, log_callback
        )
        completed_context[task.id] = content
        completed.add(task.id)
        all_completed.append(task.id)

        if save_checkpoint:
            save_checkpoint()

    return all_completed


def generate_index_file(output_dir: Path, task_list: List[AnalysisTask]) -> None:
    """生成知识库索引文件"""
    lines = [
        f"# 知识库索引",
        "",
        "本知识库由 AnswerAgent 知识库生成工作流自动生成。",
        "",
        "## 文件列表",
        "",
    ]
    for task in task_list:
        lines.append(f"- [{task.target_file}]({task.target_file}) - {task.description}")

    index_path = output_dir / "索引.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"索引文件已生成: {index_path}")