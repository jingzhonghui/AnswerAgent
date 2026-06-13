"""免登录外部流式聊天接口

POST /api/chat/external/stream

与内部接口 /api/chat/stream 的区别：
- 无需认证，任何人均可调用
- 无 conversation_id 概念，不持久化对话
- 历史上下文通过请求体中的 history 字段传入
- 不生成对话标题
- 支持 default 和 deep 两种模式

SSE 事件类型与内部接口完全一致：
kb_matched -> files_selected* -> token* -> done | error
deep 模式额外包含 agent_think / agent_observe 事件
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from core.kb_router import route_knowledge_bases
from core.file_loader import select_and_load_files, LoadedFile
from core.agent_builder import (
    build_simple_agent,
    build_kb_agent,
    build_deep_agent,
    format_history,
)
from core.llm_factory import LLMConfigError
from langchain_core.messages import HumanMessage
from models.schemas import ExternalChatRequest

logger = logging.getLogger("app.api.external_chat")

router = APIRouter(prefix="/api/chat", tags=["external-chat"])

def _merge_context(loaded_files: List[LoadedFile]) -> str:
    """将多个知识库的选中文件合并为单个上下文字符串"""
    parts = []
    for f in loaded_files:
        header = f"--- {f.kb_name}/{f.rel_path}"
        if f.truncated:
            header += " (截断)"
        parts.append(f"{header}\n{f.content}")
    return "\n\n".join(parts)


# ============================================================
# 流式生成器
# ============================================================

async def _stream_default_external(
    request: Request,
    agent,
    messages: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """默认模式流式输出（外部接口版）：DeepAgent + astream_events(v3)"""
    stream = await agent.astream_events({"messages": messages}, version="v3")

    async for msg in stream.messages:
        if await request.is_disconnected():
            return
        async for delta in msg.text:
            if await request.is_disconnected():
                return
            yield {
                "event": "token",
                "data": json.dumps({"content": delta}, ensure_ascii=False),
            }


async def _stream_deep_external(
    request: Request,
    agent,
    messages: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """深度思考模式流式输出（外部接口版）：DeepAgent + astream_events(v3)

    并发消费 stream.messages（文本 + 工具调用决策）和 stream.tool_calls（工具执行结果），
    通过 asyncio.Queue 合并保证事件时序。
    """
    stream = await agent.astream_events({"messages": messages}, version="v3")
    queue: asyncio.Queue = asyncio.Queue()

    async def collect_messages():
        """消费 stream.messages：文本 token + 工具调用决策"""
        async for msg in stream.messages:
            async for delta in msg.text:
                await queue.put(("token", delta))
            finalized = await msg.tool_calls.get()
            if finalized:
                for tc in finalized:
                    await queue.put(("agent_think", tc))

    async def collect_tool_calls():
        """消费 stream.tool_calls：工具执行结果"""
        async for call in stream.tool_calls:
            await queue.put(("agent_observe", call))

    async def run_collectors():
        try:
            await asyncio.gather(collect_messages(), collect_tool_calls())
        except Exception as e:
            logger.exception("External deep agent stream error")
            await queue.put(("error", str(e)))
        finally:
            await queue.put(("stream_done", None))

    task = asyncio.create_task(run_collectors())

    try:
        while True:
            try:
                event_type, data = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    task.cancel()
                    return
                continue

            if event_type == "stream_done":
                return
            elif event_type == "token":
                yield {
                    "event": "token",
                    "data": json.dumps({"content": data}, ensure_ascii=False),
                }
            elif event_type == "agent_think":
                yield {
                    "event": "agent_think",
                    "data": json.dumps(
                        {
                            "step": "action",
                            "thought": "",
                            "tool": data.get("name", ""),
                            "tool_input": str(data.get("args", {})),
                        },
                        ensure_ascii=False,
                    ),
                }
            elif event_type == "agent_observe":
                yield {
                    "event": "agent_observe",
                    "data": json.dumps(
                        {
                            "step": "observation",
                            "result": (
                                data.output
                                if data.completed and not data.error
                                else str(data.error)
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            elif event_type == "error":
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"message": f"深度思考执行失败: {data}"},
                        ensure_ascii=False,
                    ),
                }

    except asyncio.CancelledError:
        task.cancel()
        raise


async def _external_stream_events(
    request: Request,
    body: ExternalChatRequest,
) -> AsyncGenerator[Dict[str, str], None]:
    """外部接口 SSE 事件流生成器

    核心流程: 路由 -> 选文件 -> 构建链 -> 流式 token -> done
    不持久化任何数据。
    """
    kb_names: List[str] = []
    all_loaded: List[LoadedFile] = []

    try:
        # --- 1. 知识库路由 ---
        try:
            kb_names = route_knowledge_bases(body.message)
        except LLMConfigError as e:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": f"LLM 配置错误: {e}"},
                    ensure_ascii=False,
                ),
            }
            return
        except Exception:
            logger.exception("External KB routing failed")
            kb_names = []

        yield {
            "event": "kb_matched",
            "data": json.dumps({"kb_names": kb_names}, ensure_ascii=False),
        }

        # --- 2. 文件选取 ---
        all_files: List[str] = []
        if kb_names:
            for kb_name in kb_names:
                if await request.is_disconnected():
                    return
                try:
                    loaded = select_and_load_files(body.message, kb_name)
                except Exception:
                    logger.exception("External file selection failed for kb=%s", kb_name)
                    continue

                if loaded:
                    all_loaded.extend(loaded)
                    files = [f.rel_path for f in loaded]
                    all_files.extend(files)
                    yield {
                        "event": "files_selected",
                        "data": json.dumps(
                            {"kb": kb_name, "files": files},
                            ensure_ascii=False,
                        ),
                    }

        # --- 3. 构建上下文 ---
        context = _merge_context(all_loaded) if all_loaded else ""

        # --- 4. 格式化历史消息 + 构建 Agent ---
        formatted_history = format_history([
            {"role": h.role, "content": h.content}
            for h in body.history
        ])
        agent_messages = formatted_history + [HumanMessage(content=body.message)]

        if body.mode == "deep":
            agent = build_deep_agent(streaming=True, reasoning=True)
        elif context:
            agent = build_kb_agent(context, streaming=True)
        else:
            agent = build_simple_agent(streaming=True)

        # --- 5. 流式输出（按 mode 分发） ---
        if body.mode == "deep":
            gen = _stream_deep_external(request, agent, agent_messages)
        else:
            gen = _stream_default_external(request, agent, agent_messages)

        async for event in gen:
            yield event

        # --- 6. done 事件（无 message_id，无 title） ---
        yield {
            "event": "done",
            "data": json.dumps({}, ensure_ascii=False),
        }

    except asyncio.CancelledError:
        # 客户端主动断开连接，无需保存任何内容
        pass
    except Exception as e:
        logger.exception("External chat stream error")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"服务器内部错误: {e}"},
                ensure_ascii=False,
            ),
        }


# ============================================================
# 路由端点
# ============================================================

@router.post("/external/stream")
async def external_chat_stream(request: Request):
    """POST /api/chat/external/stream

    免登录 SSE 流式问答接口。无需认证，不持久化对话。

    Request body (JSON):
        message: str - 用户消息（必填）
        mode: str - "default" | "deep"，默认 "default"
        history: list[{"role": "user|assistant", "content": "..."}] - 可选历史消息

    Returns:
        SSE 事件流: kb_matched -> files_selected* -> token* -> done | error
    """
    # 解析请求体
    try:
        body_data = await request.json()
        body = ExternalChatRequest(**body_data)
    except Exception as e:
        async def error_gen():
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": f"请求参数错误: {e}"},
                    ensure_ascii=False,
                ),
            }
        return EventSourceResponse(error_gen())

    # 记录请求日志（不记录消息内容，仅记录元信息）
    logger.info(
        "External chat request: message_len=%d mode=%s history_rounds=%d client=%s",
        len(body.message), body.mode, len(body.history),
        request.client.host if request.client else "unknown",
    )

    return EventSourceResponse(_external_stream_events(request, body))
