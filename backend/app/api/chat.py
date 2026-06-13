"""SSE 流式问答接口

POST /api/chat/stream

处理流程:
1. 校验/创建对话，保存用户消息
2. 知识库路由 -> 发出 kb_matched
3. 文件选取 -> 发出 files_selected（每个知识库一次）
4. 构建 DeepAgent 并通过 astream_events(v3) 流式输出 -> 发出 token*
   深度思考模式额外发出 agent_think / agent_observe 事件
5. 保存助手消息 -> 发出 done
6. 异常 -> 发出 error

支持 mode=default（纯 LLM 问答）和 mode=deep（深度思考 Agent）
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from core.chat_manager import (
    chat_manager,
    ConversationNotFoundError,
)
from core.config import settings
from core.deps import get_current_user
from core.kb_router import route_knowledge_bases
from core.file_loader import select_and_load_files, LoadedFile
from core.agent_builder import (
    build_simple_agent,
    build_kb_agent,
    build_deep_agent,
    format_history,
)
from core.llm_factory import LLMConfigError, create_chat_llm
from langchain_core.messages import HumanMessage
from models.schemas import ChatStreamRequest

# 标题生成 prompt
TITLE_PROMPT = """你是一个对话标题生成助手。根据用户发送的第一条消息，生成一个简短的对话标题。

要求：
- 标题不超过15个字
- 概括用户问题的核心意图
- 直接返回标题文本，不要加引号、标点或任何解释

用户消息：{message}
标题："""

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _merge_context(loaded_files: List[LoadedFile]) -> str:
    """将多个知识库的选中文件合并为单个上下文字符串

    格式: --- kb_name/rel_path ---\ncontent\n\n
    """
    parts = []
    for f in loaded_files:
        header = f"--- {f.kb_name}/{f.rel_path}"
        if f.truncated:
            header += " (截断)"
        parts.append(f"{header}\n{f.content}")
    return "\n\n".join(parts)


async def _stream_default(
    request: Request,
    agent,
    messages: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """默认模式：使用 DeepAgent + astream_events(v3) 流式输出纯文本

    agent 是 build_simple_agent() 或 build_kb_agent(context) 返回的 CompiledStateGraph。
    """
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


async def _stream_deep(
    request: Request,
    agent,
    messages: list,
) -> AsyncGenerator[Dict[str, str], None]:
    """深度思考模式：使用 DeepAgent + astream_events(v3) 流式输出

    并发消费 stream.messages（文本 + 工具调用决策）和 stream.tool_calls（工具执行结果），
    通过 asyncio.Queue 合并，保证事件时序正确。

    agent 是 build_deep_agent() 返回的 CompiledStateGraph。
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
            logger.exception("Deep agent stream error")
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


def _generate_title(message: str) -> Optional[str]:
    """根据用户消息生成简短对话标题

    使用 LLM 概括用户问题的核心意图，生成不超过 15 字的标题。

    Args:
        message: 用户的第一条消息

    Returns:
        生成的标题字符串，失败时返回 None（调用方应使用原有标题兜底）
    """
    try:
        llm = create_chat_llm(temperature=0.1)
        prompt = TITLE_PROMPT.format(message=message)
        title = llm.invoke([HumanMessage(content=prompt)]).content.strip()
        # 清理可能的多余字符
        title = title.replace('"', '').replace('「', '').replace('」', '').replace('《', '').replace('》', '')
        # 截断过长的标题
        if len(title) > 20:
            title = title[:18] + '…'
        return title or None
    except Exception:
        logger.debug("Failed to generate title", exc_info=True)
        return None


async def _stream_events(
    request: Request,
    conversation_id: str,
    message: str,
    mode: str,
) -> AsyncGenerator[Dict[str, str], None]:
    """SSE 事件流生成器

    核心流程: 路由 -> 选文件 -> 构建 Agent -> 流式 token -> 持久化

    Yields:
        dict: {"event": str, "data": str}
    """
    kb_names: List[str] = []
    all_files: List[str] = []
    all_loaded: List[LoadedFile] = []
    full_response = ""

    try:
        # --- 0. 检测 mode=agent（未实现） ---
        if mode == "agent":
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": "Agent 模式尚未实现，请使用 mode=default 或 mode=deep"},
                    ensure_ascii=False,
                ),
            }
            return

        # --- 1. 知识库路由 ---
        try:
            kb_names = route_knowledge_bases(message)
        except LLMConfigError as e:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": f"LLM 配置错误: {e}"},
                    ensure_ascii=False,
                ),
            }
            return
        except Exception as e:
            logger.exception("KB routing failed")
            kb_names = []

        yield {
            "event": "kb_matched",
            "data": json.dumps({"kb_names": kb_names}, ensure_ascii=False),
        }

        # --- 2. 文件选取 ---
        if kb_names:
            for kb_name in kb_names:
                if await request.is_disconnected():
                    return
                try:
                    loaded = select_and_load_files(message, kb_name)
                except Exception as e:
                    logger.exception("File selection failed for kb=%s", kb_name)
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

        # --- 3. 构建 Agent + 消息 ---
        context = _merge_context(all_loaded) if all_loaded else ""

        history = chat_manager.get_recent_history(
            conversation_id, window=settings.history_window
        )
        formatted_history = format_history(history)
        agent_messages = formatted_history + [HumanMessage(content=message)]

        if mode == "deep":
            agent = build_deep_agent(streaming=True, reasoning=True)
        elif context:
            agent = build_kb_agent(context, streaming=True)
        else:
            agent = build_simple_agent(streaming=True)

        # --- 4. 流式输出（按 mode 分发） ---
        _thinking_steps: List[dict] = []

        if mode == "deep":
            gen = _stream_deep(request, agent, agent_messages)
        else:
            gen = _stream_default(request, agent, agent_messages)

        async for event in gen:
            if event["event"] == "token":
                full_response += json.loads(event["data"]).get("content", "")
            elif event["event"] == "agent_think":
                data = json.loads(event["data"])
                _thinking_steps.append({
                    "type": "action",
                    "thought": data.get("thought", ""),
                    "tool": data.get("tool", ""),
                    "toolInput": data.get("tool_input", ""),
                })
            elif event["event"] == "agent_observe":
                data = json.loads(event["data"])
                _thinking_steps.append({
                    "type": "observation",
                    "result": data.get("result", ""),
                })
            yield event

        # --- 5. 持久化助手消息 ---
        chat_manager.append_assistant_message(
            conversation_id,
            full_response,
            kb_names=kb_names if kb_names else None,
            files_used=all_files if all_files else None,
            thinking_steps=_thinking_steps if _thinking_steps else None,
        )

        # --- 6. 自动生成标题 ---
        new_title = None
        conv = chat_manager.get_conversation(conversation_id)
        if conv.title == "新对话":
            assistant_count = sum(1 for m in conv.messages if m.role == "assistant")
            if assistant_count <= 1:
                new_title = _generate_title(message)
                if new_title:
                    try:
                        chat_manager.rename_conversation(conversation_id, new_title)
                    except Exception:
                        logger.debug("Failed to rename conversation", exc_info=True)

        assistant_messages = [
            m for m in chat_manager.get_conversation(conversation_id).messages
            if m.role == "assistant"
        ]
        message_id = assistant_messages[-1].id if assistant_messages else ""

        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "message_id": message_id,
                    "title": new_title,
                },
                ensure_ascii=False,
            ),
        }

    except asyncio.CancelledError:
        # 客户端主动断开连接，保存已生成的部分内容
        if full_response.strip():
            try:
                chat_manager.append_assistant_message(
                    conversation_id,
                    full_response + "\n\n*(用户已停止生成)*",
                    kb_names=kb_names if kb_names else None,
                    files_used=all_files if all_files else None,
                )
            except Exception:
                pass
    except Exception as e:
        logger.exception("Chat stream error")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"服务器内部错误: {e}"},
                ensure_ascii=False,
            ),
        }


@router.post("/stream")
async def chat_stream(request: Request):
    """POST /api/chat/stream

    SSE 流式问答接口。需要认证。

    Request body (JSON):
        conversation_id: str - 对话 ID
        message: str - 用户消息
        mode: str - "default" | "agent"，默认 "default"

    Returns:
        SSE 事件流: kb_matched -> files_selected* -> token* -> done | error
    """
    # 手动认证（SSE async generator 不能用 Depends）
    try:
        current_user = await get_current_user(request)
    except HTTPException as e:
        async def error_gen():
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": f"认证失败: {e.detail}"},
                    ensure_ascii=False,
                ),
            }
        return EventSourceResponse(error_gen())

    # 解析请求体
    body = await request.json()
    try:
        chat_request = ChatStreamRequest(**body)
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

    conversation_id = chat_request.conversation_id
    message = chat_request.message
    mode = chat_request.mode

    # 确保对话存在且属于当前用户
    should_create = False
    try:
        conv = chat_manager.get_conversation(conversation_id)
        if conv.user_id and conv.user_id != current_user["user_id"]:
            should_create = True
    except (ConversationNotFoundError, ValueError):
        should_create = True

    if should_create:
        # 对话不存在或 ID 格式无效时自动创建新对话
        try:
            new_id = chat_manager.create_conversation(
                title="新对话", user_id=current_user["user_id"]
            )
            conversation_id = new_id
        except Exception as e:
            async def error_gen():
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"message": f"创建对话失败: {e}"},
                        ensure_ascii=False,
                    ),
                }
            return EventSourceResponse(error_gen())

    # 保存用户消息
    try:
        chat_manager.append_user_message(conversation_id, message)
    except Exception as e:
        async def error_gen():
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": f"保存用户消息失败: {e}"},
                    ensure_ascii=False,
                ),
            }
        return EventSourceResponse(error_gen())

    return EventSourceResponse(_stream_events(
        request,
        conversation_id,
        message,
        mode,
    ))