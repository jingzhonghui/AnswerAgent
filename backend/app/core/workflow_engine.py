"""工作流引擎

编排知识库生成工作流的完整生命周期：
- 状态机管理（init → preprocessing → analyzing → executing → completed/failed/paused）
- 后台异步执行（asyncio.create_task）
- 断点续传（SQLite 持久化）
- 并发控制（单任务）
- 日志管理
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from core.database import get_db
from core.workflow_preprocess import preprocess, cleanup_work_dir
from core.workflow_analyzer import scan_files, generate_task_list
from core.workflow_executor import execute_tasks, generate_index_file
from models.schemas import AnalysisTask, WorkflowTaskResponse

logger = logging.getLogger(__name__)

# 全局引擎实例
_engine: Optional[WorkflowEngine] = None


def get_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine


class WorkflowEngine:
    """知识库生成工作流引擎"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running_task: Optional[asyncio.Task] = None
        self._running_id: Optional[str] = None
        self._paused = False
        self._cancelled = False
        self._log_buffers: Dict[str, list] = {}  # task_id -> [(timestamp, line)]

    # ============================================================
    # 公开 API
    # ============================================================

    async def start(self, input_type: str, input_value: str) -> dict:
        """启动新工作流，返回 {task_id, status}"""
        if not self._lock.locked():
            if self._running_task and not self._running_task.done():
                raise RuntimeError(
                    f"已有工作流正在运行: {self._running_id}"
                )

        async with self._lock:
            task_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            async with get_db() as db:
                await db.execute(
                    """INSERT INTO kb_workflow_tasks
                       (id, status, input_type, input_value, stage, created_at, updated_at)
                       VALUES (?, 'pending', ?, ?, 'init', ?, ?)""",
                    (task_id, input_type, input_value, now, now),
                )
                await db.commit()

            self._running_id = task_id
            self._paused = False
            self._cancelled = False
            self._log_buffers[task_id] = []

            # 后台启动
            self._running_task = asyncio.create_task(self._run(task_id))

            self._log(task_id, f"工作流已创建: {task_id}")
            self._log(task_id, f"输入类型: {input_type}, 输入值: {input_value}")

            return {"task_id": task_id, "status": "processing"}

    async def pause(self, task_id: str) -> None:
        """暂停工作流"""
        if task_id != self._running_id:
            raise ValueError(f"工作流 {task_id} 未在运行")
        self._paused = True
        self._log(task_id, "收到暂停请求，当前任务完成后将暂停")

    async def resume(self, task_id: str) -> dict:
        """从断点恢复工作流"""
        async with self._lock:
            row = await self._load_task(task_id)
            if not row:
                raise ValueError(f"工作流不存在: {task_id}")

            status = row["status"]
            if status not in ("paused", "failed"):
                raise ValueError(f"工作流状态不支持恢复: {status}")

            self._running_id = task_id
            self._paused = False
            self._cancelled = False

            if task_id not in self._log_buffers:
                self._log_buffers[task_id] = []

            self._log(task_id, f"从断点恢复工作流，当前阶段: {row['stage']}")

            self._running_task = asyncio.create_task(self._run(task_id))
            return {"task_id": task_id, "status": "processing"}

    async def cancel(self, task_id: str) -> None:
        """取消正在运行的工作流"""
        if task_id == self._running_id:
            self._cancelled = True
            self._log(task_id, "收到取消请求")
        await self._update_status(task_id, "failed", error="用户取消")
        cleanup_work_dir(task_id)

    async def delete(self, task_id: str) -> None:
        """删除工作流记录（从 DB 和内存中移除）"""
        # 如果正在运行，先取消
        if task_id == self._running_id:
            self._cancelled = True
            self._log(task_id, "收到取消并删除请求")
        cleanup_work_dir(task_id)
        # 清理日志缓冲区
        self._log_buffers.pop(task_id, None)
        # 删除数据库记录
        async with get_db() as db:
            await db.execute("DELETE FROM kb_workflow_tasks WHERE id = ?", (task_id,))
            await db.commit()
        logger.info(f"工作流 {task_id} 已删除")

    async def get_status(self, task_id: str) -> WorkflowTaskResponse:
        """获取工作流状态"""
        row = await self._load_task(task_id)
        if not row:
            raise ValueError(f"工作流不存在: {task_id}")

        task_list = []
        raw_list = row.get("task_list", "[]")
        if isinstance(raw_list, str):
            try:
                raw_list = json.loads(raw_list)
            except json.JSONDecodeError:
                raw_list = []
        for item in raw_list:
            task_list.append(AnalysisTask(
                id=item["id"],
                description=item["description"],
                target_file=item["target_file"],
                dependencies=item.get("dependencies", []),
            ))

        stage_progress = {}
        raw_progress = row.get("stage_progress", "{}")
        if isinstance(raw_progress, str):
            try:
                stage_progress = json.loads(raw_progress)
            except json.JSONDecodeError:
                stage_progress = {}

        completed_tasks = []
        raw_completed = row.get("completed_tasks", "[]")
        if isinstance(raw_completed, str):
            try:
                completed_tasks = json.loads(raw_completed)
            except json.JSONDecodeError:
                completed_tasks = []

        return WorkflowTaskResponse(
            id=row["id"],
            status=row["status"],
            input_type=row["input_type"],
            input_value=row["input_value"],
            knowledge_name=row.get("knowledge_name"),
            stage=row.get("stage", "init"),
            stage_progress=stage_progress,
            task_list=task_list,
            completed_tasks=completed_tasks,
            result_path=row.get("result_path"),
            error=row.get("error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_all(self) -> list:
        """列出所有历史工作流"""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id, status, input_type, input_value, knowledge_name, "
                "stage, result_path, error, created_at, updated_at "
                "FROM kb_workflow_tasks ORDER BY created_at DESC LIMIT 50"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    def get_logs(self, task_id: str, since: int = 0) -> list:
        """获取日志条目（since 为起始索引）"""
        buffer = self._log_buffers.get(task_id, [])
        return buffer[since:]

    def get_log_lines(self, task_id: str) -> int:
        """获取日志总行数"""
        return len(self._log_buffers.get(task_id, []))

    # ============================================================
    # 内部实现
    # ============================================================

    def _log(self, task_id: str, message: str) -> None:
        """记录日志到内存缓冲区"""
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": ts, "message": message}
        if task_id not in self._log_buffers:
            self._log_buffers[task_id] = []
        self._log_buffers[task_id].append(entry)
        logger.info(f"[{task_id}] {message}")

    async def _load_task(self, task_id: str) -> Optional[dict]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM kb_workflow_tasks WHERE id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def _update_status(
        self,
        task_id: str,
        status: str,
        stage: Optional[str] = None,
        error: Optional[str] = None,
        stage_progress: Optional[dict] = None,
        task_list: Optional[list] = None,
        completed_tasks: Optional[list] = None,
        result_path: Optional[str] = None,
        knowledge_name: Optional[str] = None,
        work_dir: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            updates = ["status = ?", "updated_at = ?"]
            params = [status, now]

            if stage is not None:
                updates.append("stage = ?")
                params.append(stage)
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            if stage_progress is not None:
                updates.append("stage_progress = ?")
                params.append(json.dumps(stage_progress, ensure_ascii=False))
            if task_list is not None:
                updates.append("task_list = ?")
                params.append(json.dumps([t.model_dump() if hasattr(t, 'model_dump') else t for t in task_list], ensure_ascii=False))
            if completed_tasks is not None:
                updates.append("completed_tasks = ?")
                params.append(json.dumps(completed_tasks, ensure_ascii=False))
            if result_path is not None:
                updates.append("result_path = ?")
                params.append(result_path)
            if knowledge_name is not None:
                updates.append("knowledge_name = ?")
                params.append(knowledge_name)
            if work_dir is not None:
                updates.append("work_dir = ?")
                params.append(work_dir)

            params.append(task_id)
            await db.execute(
                f"UPDATE kb_workflow_tasks SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()

    def _check_cancelled(self) -> bool:
        return self._cancelled

    def _check_paused(self) -> bool:
        return self._paused

    async def _run(self, task_id: str) -> None:
        """主执行流程"""
        source_dir = None
        try:
            row = await self._load_task(task_id)
            if not row:
                return

            stage = row.get("stage", "init")
            input_type = row["input_type"]
            input_value = row["input_value"]

            # === 预处理阶段 ===
            if stage in ("init", "preprocessing"):
                self._log(task_id, "=== 预处理阶段 ===")
                await self._update_status(task_id, "preprocessing", stage="preprocessing")

                source_dir = preprocess(task_id, input_type, input_value)
                work_dir = str(source_dir.parent) if input_type != "local_path" else str(source_dir)
                await self._update_status(
                    task_id, "preprocessing", stage="preprocessing",
                    work_dir=work_dir,
                )
                self._log(task_id, f"预处理完成，源目录: {source_dir}")
                stage = "analyzing"

            # === 分析阶段 ===
            if stage == "analyzing":
                self._log(task_id, "=== 分析阶段 ===")
                await self._update_status(task_id, "analyzing", stage="analyzing")

                if source_dir is None:
                    work_dir_str = row.get("work_dir", "")
                    if input_type == "local_path":
                        source_dir = Path(input_value)
                    elif work_dir_str:
                        source_dir = Path(work_dir_str) / "source"
                        if not source_dir.exists():
                            source_dir = Path(work_dir_str)

                scan_result = scan_files(source_dir)
                self._log(task_id, f"文件扫描完成: {scan_result['total_files']} 个文件, {scan_result['total_size_mb']} MB")

                knowledge_name, tasks = await generate_task_list(source_dir, scan_result)
                self._log(task_id, f"LLM 分析完成，知识库名称: {knowledge_name}，任务数: {len(tasks)}")

                for t in tasks:
                    self._log(task_id, f"  任务 [{t.id}]: {t.description} → {t.target_file}")

                await self._update_status(
                    task_id, "analyzing", stage="analyzing",
                    task_list=tasks,
                    knowledge_name=knowledge_name,
                )
                stage = "executing"
                stage_progress = {"current_task_index": 0, "total_tasks": len(tasks)}

            # === 执行阶段 ===
            if stage == "executing":
                self._log(task_id, "=== 执行阶段 ===")
                await self._update_status(task_id, "executing", stage="executing")

                row = await self._load_task(task_id)
                knowledge_name = row.get("knowledge_name", "unknown")
                raw_list = row.get("task_list", "[]")
                if isinstance(raw_list, str):
                    raw_list = json.loads(raw_list)
                task_list = [
                    AnalysisTask(
                        id=item["id"],
                        description=item["description"],
                        target_file=item["target_file"],
                        dependencies=item.get("dependencies", []),
                    )
                    for item in raw_list
                ]

                completed_tasks = row.get("completed_tasks", "[]")
                if isinstance(completed_tasks, str):
                    completed_tasks = json.loads(completed_tasks)

                if source_dir is None:
                    work_dir_str = row.get("work_dir", "")
                    if input_type == "local_path":
                        source_dir = Path(input_value)
                    elif work_dir_str:
                        source_dir = Path(work_dir_str) / "source"
                        if not source_dir.exists():
                            source_dir = Path(work_dir_str)

                knowledge_path = Path(__file__).parent.parent.parent / "knowledge"
                output_dir = knowledge_path / knowledge_name

                def save_checkpoint():
                    asyncio.ensure_future(
                        self._update_status(
                            task_id, "executing", stage="executing",
                            completed_tasks=completed_tasks,
                            stage_progress=stage_progress,
                        )
                    )

                def is_cancelled():
                    return self._cancelled

                result_completed = await execute_tasks(
                    task_list=task_list,
                    source_dir=source_dir,
                    output_dir=output_dir,
                    completed_task_ids=completed_tasks,
                    log_callback=lambda msg: self._log(task_id, msg),
                    save_checkpoint=save_checkpoint,
                    is_cancelled=is_cancelled,
                )

                # 生成索引
                generate_index_file(output_dir, task_list)
                self._log(task_id, f"索引文件已生成")

                # 检查是否暂停
                if self._paused:
                    self._log(task_id, "工作流已暂停")
                    await self._update_status(
                        task_id, "paused", stage="executing",
                        completed_tasks=result_completed,
                    )
                    return

                if self._cancelled:
                    self._log(task_id, "工作流已取消")
                    await self._update_status(
                        task_id, "failed", stage="executing",
                        error="用户取消",
                        completed_tasks=result_completed,
                    )
                    cleanup_work_dir(task_id)
                    return

                result_path = str(output_dir)
                await self._update_status(
                    task_id, "completed", stage="completed",
                    result_path=result_path,
                    completed_tasks=result_completed,
                )

            self._log(task_id, f"=== 工作流完成 ===")
            self._log(task_id, f"知识库路径: {result_path}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self._log(task_id, f"错误: {error_msg}")
            logger.exception(f"工作流 {task_id} 执行失败")
            await self._update_status(
                task_id, "failed",
                error=error_msg,
            )
        finally:
            self._running_id = None
            self._running_task = None