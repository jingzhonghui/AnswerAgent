"""LCEL 问答链构建模块

构建三种问答链:
- 知识库问答链: 注入合并上下文 + 对话历史 + 当前问题
- 通用问答链: 无知识库命中时，只注入对话历史和问题
- 深度思考链: 使用推理模型 + ReAct Agent 模式，支持多步推理；
  通过 callbacks 参数实时推送中间步骤（Thought/Action/Observation）

使用 LangChain LCEL (LangChain Expression Language) 构建，
通过 .stream() 实现逐 token 流式输出。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_classic.agents import create_react_agent, create_tool_calling_agent, AgentExecutor

from core.llm_factory import create_chat_llm
from core.agent_tools import build_knowledge_search_tool


KB_SYSTEM_TEMPLATE = """\
你是一个基于本地知识库的问答助手。请根据以下参考文件内容回答用户问题。

## 规则
1. 优先使用参考文件中的信息来回答问题。
2. 如果参考文件内容不足以回答问题，可以结合你的通用知识补充，但需要明确说明哪些来自参考文件、哪些来自通用知识。
3. 引用文件内容时，请注明来自哪个文件。
4. 如果参考文件内容与问题无关，忽略它并基于通用知识回答。
5. 回答要简洁、准确，避免冗长。

## 输出格式指令（必须遵守）
根据内容特点选择以下格式，不得用纯文本段落替代：

| 内容类型 | 必须使用的格式 |
|---------|--------------|
| 对比或列举 | Markdown 表格 |
| 流程、架构、时序 | ` ```mermaid ` 代码块 |
| 数据统计或比例 | ` ```mermaid ` 代码块 |
| 代码示例 | ` ```language ` 代码块 |
| 分步骤说明 | 有序列表或 Mermaid 流程图 |
| 术语强调 | **加粗** 或 `行内代码` |

可用 Mermaid 类型：graph、flowchart、sequenceDiagram、classDiagram、pie、mindmap

## 参考文件内容
{context}"""

GENERAL_SYSTEM_TEMPLATE = """\
你是一个知识问答助手。请根据你的知识回答用户问题。

## 规则
1. 回答要简洁、准确，避免冗长。
2. 如果问题超出你的知识范围，诚实说明。

## 输出格式指令（必须遵守）
根据内容特点选择以下格式，不得用纯文本段落替代：

| 内容类型 | 必须使用的格式 |
|---------|--------------|
| 对比或列举 | Markdown 表格 |
| 流程、架构、时序 | ` ```mermaid ` 代码块 |
| 数据统计或比例 | ` ```mermaid ` 代码块 |
| 代码示例 | ` ```language ` 代码块 |
| 分步骤说明 | 有序列表或 Mermaid 流程图 |
| 术语强调 | **加粗** 或 `行内代码` |

可用 Mermaid 类型：graph、flowchart、sequenceDiagram、classDiagram、pie、mindmap"""


def build_kb_chain(context: str, streaming: bool = True):
    """构建知识库问答链

    Args:
        context: 合并后的知识库上下文（所有选中文件内容拼接）
        streaming: 是否启用流式输出

    Returns:
        LCEL Runnable: 可调用 chain.invoke({"question": ..., "history": [...]})
    """
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=KB_SYSTEM_TEMPLATE.format(context=context)),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = create_chat_llm(streaming=streaming, temperature=0.3)

    chain = prompt | llm | StrOutputParser()
    return chain


def build_general_chain(streaming: bool = True):
    """构建通用问答链（无知识库上下文）

    Args:
        streaming: 是否启用流式输出

    Returns:
        LCEL Runnable: 可调用 chain.invoke({"question": ..., "history": [...]})
    """
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=GENERAL_SYSTEM_TEMPLATE),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = create_chat_llm(streaming=streaming, temperature=0.3)

    chain = prompt | llm | StrOutputParser()
    return chain


def format_history(raw_history: List[dict]) -> list:
    """将 chat_manager 返回的历史消息转换为 LangChain 消息格式

    Args:
        raw_history: [{"role": "user", "content": "..."}, ...]

    Returns:
        list[HumanMessage | AIMessage]
    """
    messages = []
    for msg in raw_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


# ============================================================
# 深度思考（ReAct Agent）
# ============================================================

DEEP_SYSTEM_PROMPT = """\
你是一个具备深度思考能力的知识问答助手。

## 工作方式
1. **分析问题**：先拆解用户问题，明确需要哪些信息。
2. **搜索知识库**：使用 knowledge_search 工具查找相关文件内容。
3. **分析信息**：仔细分析搜索到的内容，形成初步结论。
4. **反复深入**：如果信息不足，继续搜索或搜索相关概念。
5. **给出答案**：在充分分析后给出完整的最终回答。

## 规则
1. 每次搜索都要有明确目的，说明你要搜索什么以及为什么。
2. 分析搜索结果时，引用具体文件内容来支撑你的推理。
3. 如果知识库信息不足以回答，结合你的通用知识补充，但需说明哪些来自知识库、哪些来自通用知识。
4. 回答要全面、深入，展示完整的思考过程。

## 输出格式指令（必须遵守）
根据内容特点选择以下格式，不得用纯文本段落替代：

| 内容类型 | 必须使用的格式 |
|---------|--------------|
| 对比或列举 | Markdown 表格 |
| 流程、架构、时序 | ` ```mermaid ` 代码块 |
| 数据统计或比例 | ` ```mermaid ` 代码块 |
| 代码示例 | ` ```language ` 代码块 |
| 分步骤说明 | 有序列表或 Mermaid 流程图 |
| 术语强调 | **加粗** 或 `行内代码` |

可用 Mermaid 类型：graph、flowchart、sequenceDiagram、classDiagram、pie、mindmap"""


def build_deep_chain(context: str, callbacks: list = None):
    """构建深度思考 Tool-Calling Agent 链

    使用推理模型 + Tool-Calling Agent 模式，支持多步推理-观察-行动循环。
    与 ReAct 不同，Tool-Calling Agent 使用模型原生的 function calling 能力，
    避免推理模型输出格式不兼容 ReAct 解析器的问题。

    Args:
        context: 合并后的知识库上下文（若为空则 Agent 只依赖通用知识）
        callbacks: LangChain 回调处理器列表，用于实时捕获 Agent 中间步骤

    Returns:
        AgentExecutor: 可调用 chain.invoke({"input": ..., "chat_history": [...]})
    """
    llm = create_chat_llm(streaming=True, reasoning=True)
    kb_tool = build_knowledge_search_tool(context)
    tools = [kb_tool]

    # Tool-Calling Agent 使用 ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("system", DEEP_SYSTEM_PROMPT),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=10,
        early_stopping_method="force",
        callbacks=callbacks or None,
    )