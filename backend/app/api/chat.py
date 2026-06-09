"""SSE 流式问答接口

POST /api/chat/stream

处理流程:
1. 校验/创建对话，保存用户消息
2. 知识库路由 -> 发出 kb_matched
3. 文件选取 -> 发出 files_selected（每个知识库一次）
4. 构建 LCEL 链并流式输出 -> 发出 token*
5. 保存助手消息 -> 发出 done
6. 异常 -> 发出 error

支持 mode=default（LCEL 问答链）和 mode=agent（暂未实现）
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List

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
from core.chain_builder import (
    build_kb_chain,
    build_general_chain,
    build_deep_chain,
    format_history,
)
from core.llm_factory import LLMConfigError
from langchain_core.messages import AIMessage, HumanMessage
from models.schemas import ChatStreamRequest

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
    conversation_id: str,
    context: str,
    message: str,
    formatted_history: list,
    kb_names: List[str],
    all_files: List[str],
) -> str:
    """默认模式（非深度思考）：使用 LCEL 问答链流式输出

    此函数直接 yield token 事件；return 用于返回 full_response，
    但 async generator 不能 return value，因此通过修改外层 dict 来返回。
    """
    full_response = ""

    if context:
        chain = build_kb_chain(context, streaming=True)
    else:
        chain = build_general_chain(streaming=True)

    for chunk in chain.stream({
        "question": message,
        "history": formatted_history,
    }):
        if await request.is_disconnected():
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
            return

        full_response += chunk
        yield {
            "event": "token",
            "data": json.dumps({"content": chunk}, ensure_ascii=False),
        }

    return


async def _stream_deep(
    request: Request,
    conversation_id: str,
    context: str,
    message: str,
    formatted_history: list,
    kb_names: List[str],
    all_files: List[str],
) -> str:
    """深度思考模式：使用 ReAct Agent 流式输出"""
    chain = build_deep_chain(context)
    full_response = ""

    # 将格式化后的对话历史转为字符串（React PromptTemplate 需要字符串）
    chat_history_str = ""
    for msg in formatted_history:
        if isinstance(msg, HumanMessage):
            chat_history_str += f"Human: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            chat_history_str += f"AI: {msg.content}\n"

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: chain.invoke({
                "input": message,
                "chat_history": chat_history_str,
            })
        )
        output_text = result.get("output", "") if isinstance(result, dict) else str(result)
        if output_text:
            full_response = output_text
            yield {
                "event": "token",
                "data": json.dumps({"content": output_text}, ensure_ascii=False),
            }
    except Exception as e:
        logger.exception("Deep chain invoke failed")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"深度思考执行失败: {e}"},
                ensure_ascii=False,
            ),
        }

    return


async def _stream_events(
    request: Request,
    conversation_id: str,
    message: str,
    mode: str,
) -> AsyncGenerator[Dict[str, str], None]:
    """SSE 事件流生成器

    核心流程: 路由 -> 选文件 -> 构建链 -> 流式 token -> 持久化

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

        # --- 3. 构建上下文 ---
        context = _merge_context(all_loaded) if all_loaded else ""

        history = chat_manager.get_recent_history(
            conversation_id, window=settings.history_window
        )
        formatted_history = format_history(history)

        # --- 4. 流式输出（按 mode 分发） ---
        # 子函数通过 yield 发送 token 事件，通过闭包收集 full_response
        full_response = ""
        _collector = [""]  # 闭包收集 full_response

        if mode == "deep":
            gen = _stream_deep(
                request, conversation_id, context, message, formatted_history,
                kb_names, all_files,
            )
        else:
            gen = _stream_default(
                request, conversation_id, context, message, formatted_history,
                kb_names, all_files,
            )

        async for event in gen:
            if event["event"] == "token":
                _collector[0] += json.loads(event["data"]).get("content", "")
            yield event

        full_response = _collector[0]

        # --- 5. 持久化助手消息 ---
        chat_manager.append_assistant_message(
            conversation_id,
            full_response,
            kb_names=kb_names if kb_names else None,
            files_used=all_files if all_files else None,
        )

        assistant_messages = [
            m for m in chat_manager.get_conversation(conversation_id).messages
            if m.role == "assistant"
        ]
        message_id = assistant_messages[-1].id if assistant_messages else ""

        yield {
            "event": "done",
            "data": json.dumps({"message_id": message_id}, ensure_ascii=False),
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