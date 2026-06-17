"""DeepAgents Agent 构建工厂

使用 deepagents.create_deep_agent() 替代 langchain-classic 的
create_tool_calling_agent() + AgentExecutor。

三种 Agent:
- build_simple_agent()      → 通用问答（无知识库，无工具）
- build_kb_agent(context)   → 知识库问答（上下文注入 system_prompt，无工具）
- build_deep_agent()        → 深度思考（动态工具链：list→search→read）
- build_deep_agent_legacy() → 兼容旧模式（预加载上下文 + knowledge_search 工具）
"""
from __future__ import annotations

from typing import List, Optional

from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel

from core.llm_factory import create_chat_llm
from core.agent_tools import (
    build_knowledge_search_tool,
    create_all_kb_tools,
)
from core.skill_loader import get_skill_sources


# ============================================================
# System Prompts（从 chain_builder.py 迁入）
# ============================================================

ASSISTANT_IDENTITY_PROMPT = """\
## 身份设定
你是 AnswerAgent，一个基于本地知识库和大语言模型的问答助手。
当用户询问“你是谁”“你的身份”“你是什么助手”时，优先以 AnswerAgent 的产品身份回答。
不要主动声称自己是 Claude、ChatGPT、OpenAI、Anthropic 或其他底层模型。
如果用户明确询问底层模型或模型提供商，可以说明：我的回答能力由后端配置的大语言模型提供支持。"""


def _with_identity(system_prompt: str) -> str:
    """为系统提示词追加统一产品身份。"""
    return f"{ASSISTANT_IDENTITY_PROMPT}\n\n{system_prompt}"


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

DEEP_SYSTEM_PROMPT = """\
你是一个具备深度思考能力的知识问答助手。

## 工作方式
1. **列出知识库**：首先使用 list_knowledge_bases 工具查看有哪些可用的知识库。
2. **搜索知识库**：使用 search_kb_files 工具在相关知识库中搜索信息。
3. **阅读文件**：如果搜索到相关文件，使用 read_kb_file 工具阅读完整内容。
4. **分析信息**：仔细分析获取到的内容，形成初步结论。
5. **反复深入**：如果信息不足，继续搜索或搜索相关概念。
6. **给出答案**：在充分分析后给出完整的最终回答。

## 规则
1. 优先使用本地知识库工具获取依据，不要凭空编造。
2. 每次搜索都要有明确目的，说明你要搜索什么以及为什么。
3. 分析搜索结果时，引用具体文件内容来支撑你的推理。
4. 如果知识库信息不足以回答，结合你的通用知识补充，但需说明哪些来自知识库、哪些来自通用知识。
5. 回答要全面、深入，展示完整的思考过程。
6. 不编造文件来源，引用文件必须来自工具返回结果。
7. 简单问题不要过度规划。

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


# ============================================================
# Agent 构建函数
# ============================================================

def build_simple_agent(
    streaming: bool = True,
    model: Optional[BaseChatModel] = None,
):
    """构建通用问答 Agent（无知识库、无工具）

    替代 build_general_chain()。
    使用 DeepAgents 但不注入任何工具——等效于纯 LLM 对话。

    tool_choice="none" + subagents=False 确保 Agent 不会发起工具调用。

    Args:
        streaming: 是否启用流式输出
        model: 可选覆盖 LLM 实例

    Returns:
        DeepAgent: 可调用 agent.ainvoke({"messages": [...]})
    """
    llm = model or create_chat_llm(streaming=streaming, temperature=0.3, tool_choice="none")

    agent = create_deep_agent(
        model=llm,
        system_prompt=_with_identity(GENERAL_SYSTEM_TEMPLATE),
        tools=[],
        middleware=[],
        subagents=False,
    )
    return agent


def build_kb_agent(
    context: str,
    streaming: bool = True,
    model: Optional[BaseChatModel] = None,
):
    """构建知识库问答 Agent（上下文注入 prompt，无需工具）

    替代 build_kb_chain()。
    将知识库文件内容直接注入 system_prompt，让 LLM 基于上下文回答。
    这是最高效的方式——不需要工具调用开销。

    tool_choice="none" + subagents=False 确保 Agent 不会发起工具调用。

    Args:
        context: 合并后的知识库上下文（所有选中文件内容拼接）
        streaming: 是否启用流式输出
        model: 可选覆盖 LLM 实例

    Returns:
        DeepAgent: 可调用 agent.ainvoke({"messages": [...]})
    """
    llm = model or create_chat_llm(streaming=streaming, temperature=0.3, tool_choice="none")
    system_prompt = _with_identity(KB_SYSTEM_TEMPLATE.format(context=context))

    agent = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        tools=[],
        middleware=[],
        subagents=False,
    )
    return agent


def build_deep_agent(
    streaming: bool = True,
    reasoning: bool = True,
    model: Optional[BaseChatModel] = None,
):
    """构建深度思考 Agent（动态工具链探索知识库）

    替代 build_deep_chain()。
    使用 DeepAgents + 知识库工具（list→search→read），
    Agent 可以自主探索知识库，不需要预加载上下文。

    与旧版的关键区别：
    - 不再预加载所有文件内容到上下文
    - Agent 通过工具按需访问知识库
    - 支持真正的多步推理和迭代深入

    Args:
        streaming: 是否启用流式输出
        reasoning: 是否使用推理模型（deep_* 配置）
        model: 可选覆盖 LLM 实例

    Returns:
        DeepAgent: 可调用 agent.ainvoke({"messages": [...]})
    """
    llm = model or create_chat_llm(streaming=streaming, reasoning=reasoning)
    tools = create_all_kb_tools()

    agent = create_deep_agent(
        model=llm,
        system_prompt=_with_identity(DEEP_SYSTEM_PROMPT),
        tools=tools,
        middleware=[],
        skills=get_skill_sources(),
    )
    return agent


def build_deep_agent_legacy(
    context: str,
    streaming: bool = True,
    reasoning: bool = True,
    model: Optional[BaseChatModel] = None,
):
    """构建深度思考 Agent（兼容旧模式：预加载上下文）

    行为与旧 build_deep_chain() 一致：
    - 将所有文件内容预加载到 knowledge_search 工具中
    - Agent 通过 knowledge_search 在预加载内容中搜索

    迁移过渡期使用，最终会被 build_deep_agent()（动态工具版）替代。

    Args:
        context: 合并后的知识库上下文（所有选中文件内容拼接）
        streaming: 是否启用流式输出
        reasoning: 是否使用推理模型
        model: 可选覆盖 LLM 实例

    Returns:
        DeepAgent: 可调用 agent.ainvoke({"messages": [...]})
    """
    llm = model or create_chat_llm(streaming=streaming, reasoning=reasoning)
    kb_tool = build_knowledge_search_tool(context)

    system_prompt = DEEP_SYSTEM_PROMPT.replace(
        "首先使用 list_knowledge_bases 工具查看有哪些可用的知识库",
        "使用 knowledge_search 工具查找相关文件内容"
    )

    agent = create_deep_agent(
        model=llm,
        system_prompt=_with_identity(system_prompt),
        tools=[kb_tool],
        middleware=[],
        skills=get_skill_sources(),
    )
    return agent


# ============================================================
# 消息格式转换（从 chain_builder.py 迁入）
# ============================================================

def format_history(raw_history: List[dict]) -> list:
    """将 chat_manager 返回的历史消息转换为 LangChain 消息格式

    Args:
        raw_history: [{"role": "user", "content": "..."}, ...]

    Returns:
        list[HumanMessage | AIMessage]
    """
    from langchain_core.messages import AIMessage, HumanMessage

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
# DeepAgent 调用辅助
# ============================================================

def build_messages(
    system_prompt: str,
    history: list,
    question: str,
) -> list:
    """构建 DeepAgent 标准的 messages 输入格式

    DeepAgents 使用 {"messages": [...]} 格式，所有内容（包括 system prompt、
    历史消息、当前问题）统一放入 messages 列表。

    Args:
        system_prompt: 系统提示词
        history: 已格式化的历史消息列表
        question: 用户当前问题

    Returns:
        list[dict]: 包含 system + history + user 的消息列表
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(history)
    messages.append(HumanMessage(content=question))
    return messages