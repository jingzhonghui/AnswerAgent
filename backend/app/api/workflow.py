"""知识库生成工作流 API 路由

提供工作流的启动、暂停、恢复、取消、状态查询和日志 SSE 流。
所有端点需要管理员认证。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse

from core.deps import get_current_admin_user
from core.workflow_engine import get_engine
from models.schemas import WorkflowStartRequest, WorkflowStartResponse

router = APIRouter(prefix="/api/admin/workflow", tags=["admin-workflow"])


# ============================================================
# 启动工作流
# ============================================================

@router.post("/start", response_model=WorkflowStartResponse)
async def start_workflow(
    data: WorkflowStartRequest,
    admin: dict = Depends(get_current_admin_user),
):
    """启动知识库生成工作流（路径/Git 方式）"""
    engine = get_engine()
    try:
        result = await engine.start(data.input_type, data.input_value)
        return WorkflowStartResponse(task_id=result["task_id"], status=result["status"])
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/start/upload", response_model=WorkflowStartResponse)
async def start_workflow_upload(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin_user),
):
    """上传压缩包并启动知识库生成工作流"""
    # 保存上传文件到临时目录
    upload_dir = Path(tempfile.gettempdir()) / "answeragent_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "upload.zip").suffix
    if suffix not in (".zip", ".gz", ".tgz", ".tar.gz"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的压缩格式: {suffix}，支持 .zip / .tar.gz / .tgz",
        )

    tmp_path = upload_dir / f"{os.urandom(8).hex()}{suffix}"
    try:
        content = await file.read()
        if len(content) > 500 * 1024 * 1024:  # 500MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="上传文件大小不能超过 500MB",
            )
        tmp_path.write_bytes(content)

        engine = get_engine()
        try:
            result = await engine.start("archive", str(tmp_path))
            return WorkflowStartResponse(task_id=result["task_id"], status=result["status"])
        except RuntimeError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        pass  # 文件保留给预处理阶段使用


# ============================================================
# 状态查询
# ============================================================

@router.get("/status/{task_id}")
async def get_workflow_status(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """获取工作流状态"""
    engine = get_engine()
    try:
        return await engine.get_status(task_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/list")
async def list_workflows(
    admin: dict = Depends(get_current_admin_user),
):
    """列出所有工作流"""
    engine = get_engine()
    return await engine.list_all()


# ============================================================
# 控制操作
# ============================================================

@router.post("/pause/{task_id}")
async def pause_workflow(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """暂停工作流"""
    engine = get_engine()
    try:
        await engine.pause(task_id)
        return {"message": "暂停请求已发送"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/resume/{task_id}")
async def resume_workflow(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """从断点恢复工作流"""
    engine = get_engine()
    try:
        result = await engine.resume(task_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """删除工作流（运行中的先取消再删除）"""
    engine = get_engine()
    try:
        # 检查状态：运行中/暂停 → 先取消；已完成/失败 → 直接删除
        task_status = await engine.get_status(task_id)
        if task_status.status in ("preprocessing", "analyzing", "executing", "paused"):
            await engine.cancel(task_id)
        await engine.delete(task_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============================================================
# 日志 SSE
# ============================================================

@router.get("/log/{task_id}")
async def stream_workflow_log(
    task_id: str,
    request: Request,
    admin: dict = Depends(get_current_admin_user),
):
    """SSE 流式推送工作流日志"""
    engine = get_engine()

    async def event_generator():
        last_index = 0
        finished = False
        try:
            while not finished:
                # 检查客户端断开
                if await request.is_disconnected():
                    break

                # 获取新日志
                logs = engine.get_logs(task_id, last_index)
                for entry in logs:
                    data = json.dumps({
                        "type": "log",
                        "timestamp": entry["timestamp"],
                        "message": entry["message"],
                    }, ensure_ascii=False)
                    yield f"event: log\ndata: {data}\n\n"
                    last_index += 1

                # 检查工作流是否结束
                try:
                    status = await engine.get_status(task_id)
                    if status.status in ("completed", "failed"):
                        yield f"event: done\ndata: {json.dumps({'type': 'done', 'status': status.status})}\n\n"
                        finished = True
                except ValueError:
                    finished = True

                if not finished:
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )