"""SSE 流式问答接口

POST /api/chat/stream

处理流程:
1. 校验/创建对话，保存用户消息
2. 知识库路由 -> 发出 kb_matched
3. 文件选取 -> 发出 files_selected（每个知识库一次）
4. 构建 LCEL 链并流式输出 -> 发出 token*
   深度思考模式额外发出 agent_think / agent_observe 事件
5. 保存助手消息 -> 发出 done
6. 异常 -> 发出 error

支持 mode=default（LCEL 问答链）和 mode=deep（ReAct Agent 深度思考）
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

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
from core.llm_factory import LLMConfigError, create_chat_llm
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
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


# ============================================================
# 深度思考回调处理器 — 桥接同步 Agent 回调与异步 SSE 流
# ============================================================

SENTINEL = object()

class _DeepThinkingCallback(BaseCallbackHandler):
    """捕获 Agent 每一步 Thought/Action/Observation 并推入 asyncio.Queue。

    Agent 完成或异常时会推入 sentinel 标记，通知主循环可以结束。
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._queue = queue
        self._loop = loop

    def _push(self, item: dict) -> None:
        """线程安全地将事件推入队列"""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def _push_sentinel(self) -> None:
        """通知主循环 Agent 已完成（正常或异常）"""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, SENTINEL)

    def on_agent_action(
        self,
        action: AgentAction,
        **kwargs: Any,
    ) -> None:
        """Agent 决定执行某个工具时触发"""
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

    def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> None:
        """工具执行完毕时触发（Observation）"""
        self._push({
            "event": "agent_observe",
            "data": json.dumps(
                {"step": "observation", "result": output},
                ensure_ascii=False,
            ),
        })

    def on_agent_finish(
        self,
        finish: AgentFinish,
        **kwargs: Any,
    ) -> None:
        """Agent 完成时触发 — 先推送最终回答，再推送 sentinel"""
        output = finish.return_values.get("output", "")
        self._push({
            "event": "agent_finish",
            "data": json.dumps(
                {"output": output},
                ensure_ascii=False,
            ),
        })
        # sentinel 必须在 agent_finish 之后推送，确保主循环先消费完 finish 事件
        self._push_sentinel()


def _clean_thought(log_text: str) -> str:
    """从 AgentAction.log 中提取纯思考文本，去掉 Action/Action Input 行"""
    if not log_text:
        return ""
    # 去掉 "Action: ..." 和 "Action Input: ..." 行，保留前面的 Thought 或纯文本
    cleaned = re.split(r'\n\s*(?:Action|Thought)\s*:', log_text, maxsplit=1)[0].strip()
    return cleaned


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


async def _stream_deep(
    request: Request,
    conversation_id: str,
    context: str,
    message: str,
    formatted_history: list,
    kb_names: List[str],
    all_files: List[str],
) -> AsyncGenerator[Dict[str, str], None]:
    """深度思考模式：使用 Tool-Calling Agent 流式输出

    通过回调 + asyncio.Queue 实时推送 Agent 的思考过程：
    - agent_think: Agent 的推理/行动决策
    - agent_observe: 工具执行结果
    - agent_finish: 最终回答（转为 token 发出）
    - error: 异常

    Agent 正常或异常结束时回调会推送 sentinel 到队列，
    主循环收到 sentinel 后退出，不再依赖超时轮询。
    """
    # Tool-Calling Agent 使用 MessagesPlaceholder，直接传 LangChain 消息列表
    chat_history = formatted_history

    queue: asyncio.Queue = asyncio.Queue()
    callback = _DeepThinkingCallback(queue, asyncio.get_event_loop())
    chain = build_deep_chain(context, callbacks=[callback])

    loop = asyncio.get_event_loop()

    def _run_agent():
        """在 executor 线程中同步执行 Agent。正常完成时回调已发送 sentinel；
        异常由 finally 兜底发送 sentinel。
        """
        try:
            chain.invoke({
                "input": message,
                "chat_history": chat_history,
            })
        finally:
            # 无论正常还是异常，确保 sentinel 一定被推送
            # 使用外层保存的 loop，避免 executor 线程中 get_event_loop() 抛 RuntimeError
            loop.call_soon_threadsafe(
                queue.put_nowait, SENTINEL,
            )

    # 在 executor 中启动 Agent（不 await，让它后台跑）
    task = asyncio.get_event_loop().run_in_executor(None, _run_agent)

    try:
        while True:
            # 带超时等待队列事件 — sentinel 机制保证正常结束不依赖超时；
            # 超时仅用于定期检查客户端断开
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
            except asyncio.TimeoutError:
                # 超时不是错误：检查客户端是否断开了
                if await request.is_disconnected():
                    task.cancel()
                    return
                continue

            # sentinel 到达 → 退出主循环
            if event is SENTINEL:
                # 在退出前排空队列中可能遗留的事件（例如 agent_finish 在 sentinel 之前）
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
                # 检查 executor 是否抛了异常（正常完成时 exception() 会抛 InvalidStateError）
                try:
                    exc = task.exception()
                except asyncio.InvalidStateError:
                    exc = None
                if exc:
                    logger.exception("Deep chain invoke failed")
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"message": f"深度思考执行失败: {exc}"},
                            ensure_ascii=False,
                        ),
                    }
                return

            # 收到 agent_finish 事件 → 转为 token 发出
            if event["event"] == "agent_finish":
                data = json.loads(event["data"])
                output_text = data.get("output", "")
                if output_text:
                    yield {
                        "event": "token",
                        "data": json.dumps({"content": output_text}, ensure_ascii=False),
                    }
                continue

            # 收到 error 事件
            if event["event"] == "error":
                yield event
                continue

            # agent_think / agent_observe → 直接透传给前端
            yield event

    except asyncio.CancelledError:
        task.cancel()
        raise
    except Exception as e:
        logger.exception("Deep stream error")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"深度思考执行失败: {e}"},
                ensure_ascii=False,
            ),
        }


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
        full_response = ""
        _collector = [""]  # 闭包收集 full_response
        _thinking_steps: List[dict] = []  # 闭包收集深度思考步骤

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
            # agent_think / agent_observe 事件直接透传给前端
            yield event

        full_response = _collector[0]

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
            # 检查这是否是对话中的第一条助手回复
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