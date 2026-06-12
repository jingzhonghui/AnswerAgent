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
from typing import Any, AsyncGenerator, Dict, List

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from core.kb_router import route_knowledge_bases
from core.file_loader import select_and_load_files, LoadedFile
from core.chain_builder import (
    build_kb_chain,
    build_general_chain,
    build_deep_chain,
    format_history,
)
from core.llm_factory import LLMConfigError
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
from models.schemas import ExternalChatRequest

logger = logging.getLogger("app.api.external_chat")

router = APIRouter(prefix="/api/chat", tags=["external-chat"])

SENTINEL = object()


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
# 深度思考回调处理器（与 chat.py 中相同逻辑）
# ============================================================

class _DeepThinkingCallback(BaseCallbackHandler):
    """捕获 Agent 每一步 Thought/Action/Observation 并推入 asyncio.Queue"""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._queue = queue
        self._loop = loop

    def _push(self, item: dict) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def _push_sentinel(self) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, SENTINEL)

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        self._push({
            "event": "agent_think",
            "data": json.dumps(
                {
                    "step": "action",
                    "thought": getattr(action, "log", "") or "",
                    "tool": action.tool,
                    "tool_input": str(action.tool_input),
                },
                ensure_ascii=False,
            ),
        })

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self._push({
            "event": "agent_observe",
            "data": json.dumps(
                {"step": "observation", "result": output},
                ensure_ascii=False,
            ),
        })

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        output = finish.return_values.get("output", "")
        self._push({
            "event": "agent_finish",
            "data": json.dumps({"output": output}, ensure_ascii=False),
        })
        self._push_sentinel()


# ============================================================
# 流式生成器
# ============================================================

async def _stream_default_external(
    request: Request,
    context: str,
    message: str,
    formatted_history: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """默认模式流式输出（外部接口版，无持久化）"""
    if context:
        chain = build_kb_chain(context, streaming=True)
    else:
        chain = build_general_chain(streaming=True)

    for chunk in chain.stream({
        "question": message,
        "history": formatted_history,
    }):
        if await request.is_disconnected():
            return

        yield {
            "event": "token",
            "data": json.dumps({"content": chunk}, ensure_ascii=False),
        }


async def _stream_deep_external(
    request: Request,
    context: str,
    message: str,
    formatted_history: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """深度思考模式流式输出（外部接口版，无持久化）"""
    chat_history = formatted_history

    queue: asyncio.Queue = asyncio.Queue()
    callback = _DeepThinkingCallback(queue, asyncio.get_event_loop())
    chain = build_deep_chain(context, callbacks=[callback])

    loop = asyncio.get_event_loop()

    def _run_agent():
        try:
            chain.invoke({
                "input": message,
                "chat_history": chat_history,
            })
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    task = asyncio.get_event_loop().run_in_executor(None, _run_agent)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    task.cancel()
                    return
                continue

            if event is SENTINEL:
                while not queue.empty():
                    late_event: dict = queue.get_nowait()
                    if late_event is SENTINEL:
                        continue
                    if late_event["event"] == "agent_finish":
                        data = json.loads(late_event["data"])
                        output_text = data.get("output", "")
                        if output_text:
                            yield {
                                "event": "token",
                                "data": json.dumps({"content": output_text}, ensure_ascii=False),
                            }
                    else:
                        yield late_event

                try:
                    exc = task.exception()
                except asyncio.InvalidStateError:
                    exc = None
                if exc:
                    logger.exception("External deep chain invoke failed")
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"message": f"深度思考执行失败: {exc}"},
                            ensure_ascii=False,
                        ),
                    }
                return

            if event["event"] == "agent_finish":
                data = json.loads(event["data"])
                output_text = data.get("output", "")
                if output_text:
                    yield {
                        "event": "token",
                        "data": json.dumps({"content": output_text}, ensure_ascii=False),
                    }
                continue

            if event["event"] == "error":
                yield event
                continue

            yield event

    except asyncio.CancelledError:
        task.cancel()
        raise
    except Exception as e:
        logger.exception("External deep stream error")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"深度思考执行失败: {e}"},
                ensure_ascii=False,
            ),
        }


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

        # --- 4. 格式化历史消息 ---
        formatted_history = format_history([
            {"role": h.role, "content": h.content}
            for h in body.history
        ])

        # --- 5. 流式输出（按 mode 分发） ---
        if body.mode == "deep":
            gen = _stream_deep_external(
                request, context, body.message, formatted_history,
            )
        else:
            gen = _stream_default_external(
                request, context, body.message, formatted_history,
            )

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
