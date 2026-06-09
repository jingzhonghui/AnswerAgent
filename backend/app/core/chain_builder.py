"""LCEL 问答链构建模块

构建两种问答链:
- 知识库问答链: 注入合并上下文 + 对话历史 + 当前问题
- 通用问答链: 无知识库命中时，只注入对话历史和问题

使用 LangChain LCEL (LangChain Expression Language) 构建，
通过 .stream() 实现逐 token 流式输出。
"""
from __future__ import annotations

from typing import List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from core.llm_factory import create_chat_llm


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