# DeepAgents 升级任务拆分计划

## Context

当前项目已完成 LangChain 六阶段开发（工程骨架、对话 CRUD、知识库检索、LCEL 问答链、Vue3 前端、端到端联调），并实现了基于 `langchain-classic` 的 `AgentExecutor` 深度思考模式。

本计划的目标是将 LangChain Agent 体系全面升级为 DeepAgents（`deepagents`），替换以下核心模块：

| 当前实现 | 升级后 |
|---------|--------|
| `chain_builder.py` — LCEL 链 + `create_tool_calling_agent` + `AgentExecutor` | `agent_builder.py` — 统一使用 `create_deep_agent()` |
| `chat.py` — 自定义 `_DeepThinkingCallback` + 线程池 + `asyncio.Queue` 桥接 | `agent_stream.py` — LangGraph 原生 `astream_events` |
| `external_chat.py` — 同上 | 同上 |
| `langchain-classic` 依赖 | 移除，替换为 `deepagents` |

## 关键设计决策

- **保留 LangChain provider 层**：`ChatOpenAI`、`ChatAnthropic`、`HumanMessage`、`SystemMessage` 继续使用，DeepAgents 构建于其上。
- **保留 `default` 和 `deep` 双模式**：`default` 模式仍走简单 LCEL 链（轻量快速），`deep` 模式走 DeepAgents（工具调用 + 子代理）。
- **SSE 协议保持兼容**：事件类型（`kb_matched`、`files_selected`、`token`、`agent_think`、`agent_observe`、`done`、`error`）不变，前端无需改动。
- **安全边界不变**：不开放通用文件读写、shell execute、`.env` 读取、`data/conversations` 直接访问、`knowledge` 写入。
- **DeepAgents 自带 middleware 需显式关闭**：FilesystemMiddleware、TodoListMiddleware 默认关闭，只保留自定义知识库工具。

## 总体开发顺序

1. 环境准备与技术验证 — 安装 DeepAgents，验证 API 兼容性
2. 拆出 `agent_tools.py` — 从 `chain_builder.py` 拆出知识库工具
3. 新增 `agent_builder.py` — DeepAgents 工厂函数
4. 新增 `agent_stream.py` — LangGraph 事件 → SSE 事件转换
5. 重构 `chat.py` — 用 DeepAgents 流式替换旧逻辑
6. 重构 `external_chat.py` — 同上
7. 清理旧代码与依赖更新
8. 测试更新与验证
9. 前端适配（可选增强）

---

## 阶段 0：环境准备与技术验证

### 目标

在独立分支上安装 DeepAgents，编写探针脚本验证与现有技术栈的兼容性，确认 API 形态后再开始迁移。

### 关键文件

- `backend/requirements.txt`
- `backend/tests/test_deepagents_probe.py`（新增，验证后删除或保留）

### 任务

#### 任务 0.1：创建升级分支

```bash
git checkout -b feature/deepagents-upgrade
```

#### 任务 0.2：安装 DeepAgents 并锁定版本

- 安装 `deepagents` 及其依赖（`langgraph` 等）
- 确认与现有 `langchain-openai`、`langchain-anthropic` 版本兼容
- 锁定版本号到 `requirements.txt`

```diff
# requirements.txt
+ deepagents>=0.1.0
+ langgraph>=0.2.0
```

#### 任务 0.3：编写探针测试 `backend/tests/test_deepagents_probe.py`

验证以下能力：

1. `create_deep_agent()` 基本创建（用 `ChatOpenAI`）
2. `ChatAnthropic` 兼容性（tool calling 是否正常）
3. 自定义 `@tool` 装饰器工具兼容性
4. `agent.astream_events()` 流式输出事件结构
5. `system_prompt` 参数是否生效
6. `middleware` 参数用法（确认如何关闭默认 middleware）
7. DeepAgents 消息格式（`{"messages": [...]}` vs 旧格式）

#### 任务 0.4：记录 API 差异

将探针测试中发现的 API 差异记录到本文档的"API 差异附录"部分。

### 验收标准

- `pip install -r requirements.txt` 无依赖冲突
- 后端能正常启动，`/api/health` 返回正常
- 探针脚本全部通过
- API 差异已记录，后续迁移有据可查

---

## 阶段 1：拆出 `agent_tools.py`

### 目标

将 `chain_builder.py` 中的 `_build_knowledge_search_tool()` 和相关工具逻辑拆到独立模块，方便 DeepAgents 复用。

### 关键文件

- `backend/app/core/agent_tools.py`（新增）
- `backend/app/core/chain_builder.py`（修改）

### 任务

#### 任务 1.1：新增 `agent_tools.py`

从 `chain_builder.py` 迁移 `_build_knowledge_search_tool`，并新增更多受控知识库工具：

```python
# agent_tools.py 工具清单

build_knowledge_search_tool(kb_context: str) -> Tool
# 迁移自 chain_builder._build_knowledge_search_tool
# 在知识库上下文中按关键词搜索

list_knowledge_bases_tool() -> Tool
# 新增：列出所有可用知识库名称
# 底层调用 kb_router.list_knowledge_bases()

route_knowledge_tool(question: str) -> Tool
# 新增：对问题做知识库路由匹配
# 底层调用 kb_router.route_knowledge_bases()

search_kb_files_tool(kb_name: str, query: str) -> Tool
# 新增：在指定知识库中搜索文件内容
# 底层调用 file_loader 逻辑

read_kb_file_tool(kb_name: str, rel_path: str) -> Tool
# 新增：读取知识库中指定文件的完整内容
# 底层调用 file_loader._read_file_safely()
```

#### 任务 1.2：保持 `chain_builder.py` 向后兼容

- `chain_builder.py` 中的 `build_deep_chain()` 改为从 `agent_tools` 导入工具
- 不删除 `chain_builder.py`（阶段 5 再清理）

### 验收标准

- 所有工具函数可正常创建并返回 `Tool` 实例
- `build_deep_chain()` 使用新工具后行为不变
- 现有测试全部通过
- 工具描述清晰，Agent 能理解何时调用

---

## 阶段 2：新增 `agent_builder.py`

### 目标

创建 DeepAgents 版本的 Agent 构建工厂，替代 `chain_builder.py` 中的 Agent 构建逻辑。

### 关键文件

- `backend/app/core/agent_builder.py`（新增）
- `backend/app/core/agent_tools.py`（依赖）
- `backend/app/core/llm_factory.py`（可能修改）

### 任务

#### 任务 2.1：实现 `build_simple_agent()`

```python
def build_simple_agent(streaming: bool = True):
    """构建简单问答 Agent（无工具，纯对话）
    
    替代 build_general_chain()。
    使用 DeepAgents 但关闭所有 middleware 和工具。
    等效于普通的 prompt → LLM 流程。
    """
```

#### 任务 2.2：实现 `build_kb_agent()`

```python
def build_kb_agent(context: str, streaming: bool = True):
    """构建知识库问答 Agent（带上下文，无工具调用）
    
    替代 build_kb_chain()。
    将知识库上下文注入 system_prompt。
    不需要工具，因为上下文已在 prompt 中。
    """
```

#### 任务 2.3：实现 `build_deep_agent()`

```python
def build_deep_agent(context: str):
    """构建深度思考 Agent（带工具 + 子代理）
    
    替代 build_deep_chain()。
    配置：
    - 注入知识库搜索工具
    - 注入 DeepAgents 子代理（可选，初期关闭）
    - 关闭 FilesystemMiddleware
    - 关闭 TodoListMiddleware（初期）
    - 设置 max_iterations 等效限制
    """
```

#### 任务 2.4：处理 DeepAgents 特有的配置

- **关闭默认 middleware**：DeepAgents 默认带 FilesystemMiddleware 和 TodoListMiddleware，需要显式关闭或替换
- **消息格式适配**：DeepAgents 使用 `{"messages": [...]}` 格式，需要适配 `format_history()`
- **迭代限制**：DeepAgents 没有 `max_iterations`，需要通过 `recursion_limit` 或自定义 middleware 限制

#### 任务 2.5：可能修改 `llm_factory.py`

- 如果 DeepAgents 对模型有特殊要求（如必须支持 tool calling），增加校验
- 新增 `create_agent_model()` 方法，封装 Agent 场景的模型配置

### 验收标准

- `build_simple_agent()` 能正常创建并响应问题
- `build_kb_agent()` 能利用注入的上下文回答
- `build_deep_agent()` 能调用知识库搜索工具
- 三种 Agent 的 `astream_events()` 均能正常流式输出
- 不使用 `AgentExecutor`、`create_tool_calling_agent` 等旧 API

---

## 阶段 3：新增 `agent_stream.py`

### 目标

将 LangGraph 的 `astream_events` 事件流转换为项目现有的 SSE 事件协议，封装为可复用的适配器。

### 关键文件

- `backend/app/core/agent_stream.py`（新增）

### 任务

#### 任务 3.1：实现 `AgentStreamAdapter` 类

```python
class AgentStreamAdapter:
    """将 LangGraph astream_events 事件转换为 SSE 事件
    
    LangGraph 事件类型 → SSE 事件类型：
    - on_chat_model_stream → token
    - on_tool_start → agent_think
    - on_tool_end → agent_observe
    - on_chain_end (agent 完成) → sentinel
    - on_chain_stream (自定义) → kb_matched / files_selected
    """
    
    def __init__(self, agent, input_data: dict):
        ...
    
    async def astream(self) -> AsyncGenerator[dict, None]:
        """异步生成 SSE 事件 dict"""
        ...
```

#### 任务 3.2：处理事件映射细节

| LangGraph 事件 | 条件 | SSE 事件 |
|---------------|------|---------|
| `on_chat_model_stream` | `event["metadata"]["langgraph_node"] == "agent"` | `token` |
| `on_tool_start` | 工具名包含 `knowledge` | `agent_think` |
| `on_tool_end` | 工具名包含 `knowledge` | `agent_observe` |
| `on_tool_start` | 工具名 = `route_knowledge_bases` | `kb_matched`（注入 data） |
| `on_tool_end` | 工具名 = `search_kb_files` | `files_selected`（注入 data） |
| `on_chain_end` | output 包含最终回答 | 流结束标记 |
| 异常 | 任何步骤 | `error` |

#### 任务 3.3：处理客户端断开

- 在 `astream()` 中接受 `Request` 参数，定期检查 `request.is_disconnected()`
- 断开时取消 Agent 执行（通过 LangGraph 的 cancel 机制）

### 验收标准

- 事件映射正确，与现有 SSE 协议完全兼容
- 客户端断开时能优雅停止
- 异常能正确包装为 `error` 事件

---

## 阶段 4：重构 `chat.py`

### 目标

将 `chat.py` 中的流式逻辑改为使用 `agent_builder` + `agent_stream`，删除旧的 `AgentExecutor` + 回调 + 线程池 逻辑。

### 关键文件

- `backend/app/api/chat.py`（重构）

### 任务

#### 任务 4.1：删除旧代码

需删除的内容：

- `_DeepThinkingCallback` 类（~50 行）
- `SENTINEL` 常量
- `_clean_thought()` 函数
- `_stream_default()` 中 LCEL `chain.stream()` 调用
- `_stream_deep()` 中的线程池 + `asyncio.Queue` + 回调逻辑
- `from langchain_core.callbacks import BaseCallbackHandler`
- `from langchain_core.agents import AgentAction, AgentFinish`

#### 任务 4.2：新增 `_stream_agent()` 统一方法

```python
async def _stream_agent(
    request: Request,
    agent_type: str,  # "simple" | "kb" | "deep"
    context: str,
    message: str,
    formatted_history: list,
    kb_names: List[str],
    all_files: List[str],
) -> AsyncGenerator[Dict[str, str], None]:
    """统一的 Agent 流式输出
    
    使用 AgentStreamAdapter 消费 DeepAgents 事件。
    """
```

#### 任务 4.3：更新 `_stream_events()` 主流程

```diff
- if mode == "deep":
-     gen = _stream_deep(...)
- else:
-     gen = _stream_default(...)
+ if context:
+     gen = _stream_agent(request, "kb", context, ...)
+ else:
+     gen = _stream_agent(request, "simple", "", ...)
```

#### 任务 4.4：保留 `_generate_title()` 不变

标题生成逻辑无需修改。

### 验收标准

- `mode=default` 行为与升级前完全一致
- `mode=deep` 行为与升级前功能等价（SSE 事件类型和顺序一致）
- 不再依赖 `langchain-classic` 的任何 Agent 类型
- 不再使用线程池执行 Agent
- 不再使用 `asyncio.Queue` 桥接

---

## 阶段 5：重构 `external_chat.py`

### 目标

与 `chat.py` 同样的重构，但跳过持久化逻辑。

### 关键文件

- `backend/app/api/external_chat.py`（重构）

### 任务

#### 任务 5.1：与 `chat.py` 阶段 4 同步重构

- 删除 `_DeepThinkingCallback` 类
- 删除 `SENTINEL` 常量
- 删除线程池 + 队列逻辑
- 新增统一的 `_stream_agent_external()` 方法
- 复用 `AgentStreamAdapter`

#### 任务 5.2：提取共享代码（可选）

如果 `chat.py` 和 `external_chat.py` 的流式逻辑重复过多，考虑提取到 `agent_stream.py` 中的共享函数。

### 验收标准

- 外部接口 SSE 行为不变
- 无持久化逻辑泄漏
- 代码与 `chat.py` 保持一致的风格

---

## 阶段 6：清理旧代码与依赖更新

### 目标

删除不再需要的旧模块，更新依赖清单，确保无遗留引用。

### 关键文件

- `backend/requirements.txt`（修改）
- `backend/app/core/chain_builder.py`（删除或重命名）
- `backend/app/main.py`（修改 import）
- `CLAUDE.md`（更新）

### 任务

#### 任务 6.1：更新 `requirements.txt`

```diff
- langchain-classic
+ deepagents>=0.1.0
+ langgraph>=0.2.0
# 保留：
# langchain-openai
# langchain-anthropic
# langchain-community
```

#### 任务 6.2：清理 `chain_builder.py`

- 方案 A：删除 `chain_builder.py`，所有引用改为 `agent_builder`
- 方案 B：保留 `chain_builder.py` 但标记 deprecated，默认使用 `agent_builder`

建议方案 A（彻底清理）。

#### 任务 6.3：更新所有 import 引用

```bash
# 搜索所有引用 chain_builder 的文件
grep -r "chain_builder" backend/
grep -r "langchain_classic" backend/
grep -r "AgentExecutor" backend/
grep -r "create_tool_calling_agent" backend/
```

逐一更新或删除。

#### 任务 6.4：更新项目文档

- `CLAUDE.md`：更新架构描述，反映 DeepAgents 替代 LangChain Agent
- `docs/设计方案.md`：更新第 6 节"Deep Agents 可选复杂任务模式"为"已实现"

### 验收标准

- `grep -r "chain_builder" backend/` 无结果（或仅剩注释）
- `grep -r "langchain_classic" backend/` 无结果
- `grep -r "AgentExecutor" backend/` 无结果
- `pip install -r requirements.txt` 不安装 `langchain-classic`
- 后端启动无 import 错误

---

## 阶段 7：测试更新与验证

### 目标

更新测试用例，确保升级后功能正常，新增 DeepAgents 相关测试。

### 关键文件

- `backend/tests/conftest.py`（可能修改）
- `backend/tests/test_agent_builder.py`（新增）
- `backend/tests/test_agent_tools.py`（新增）
- `backend/tests/test_agent_stream.py`（新增）
- `backend/tests/test_chat_manager.py`（不变）
- `backend/tests/test_file_loader.py`（不变）
- `backend/tests/test_kb_router.py`（不变）

### 任务

#### 任务 7.1：更新 `conftest.py`

- 新增 `deepagents` 相关的 fixture（如 mock LLM 用于 Agent 测试）
- 确保现有 fixture 不受影响

#### 任务 7.2：新增 `test_agent_tools.py`

- 测试 `build_knowledge_search_tool()` 返回正确的 Tool
- 测试 `list_knowledge_bases_tool()` 行为
- 测试 `search_kb_files_tool()` 路径安全
- 测试 `read_kb_file_tool()` 路径安全

#### 任务 7.3：新增 `test_agent_builder.py`

- 测试 `build_simple_agent()` 创建成功
- 测试 `build_kb_agent()` 上下文注入
- 测试 `build_deep_agent()` 工具绑定
- 测试 middleware 是否正确关闭
- 测试消息格式适配

#### 任务 7.4：新增 `test_agent_stream.py`

- 测试 `AgentStreamAdapter` 事件映射
- 测试 `token` 事件正确生成
- 测试 `agent_think` / `agent_observe` 事件正确生成
- 测试异常处理
- 测试客户端断开

#### 任务 7.5：确保现有测试全部通过

- `test_chat_manager.py` — 应全部通过（无变更）
- `test_file_loader.py` — 应全部通过（无变更）
- `test_kb_router.py` — 应全部通过（无变更）

### 验收标准

- `pytest` 全部通过，0 失败
- 新增测试覆盖所有新模块的核心路径
- 旧测试无回归

---

## 阶段 8：前端适配（可选增强）

### 目标

在 SSE 协议兼容的基础上，新增可选的 Agent Trace 面板，展示完整执行轨迹。

### 关键文件

- `frontend/src/types/index.ts`
- `frontend/src/api/index.ts`
- `frontend/src/stores/chat.ts`
- `frontend/src/components/ChatWindow.vue`（或新增 `AgentTrace.vue`）

### 任务

#### 任务 8.1：新增 `agent_trace` SSE 事件

后端 `agent_stream.py` 新增事件类型：

```json
{
  "event": "agent_trace",
  "data": {
    "steps": [
      {"type": "think", "content": "需要先搜索知识库..."},
      {"type": "tool_call", "tool": "knowledge_search", "input": "SSE协议"},
      {"type": "tool_result", "output": "找到 3 个相关文件..."},
      {"type": "answer", "content": "根据知识库..."}
    ]
  }
}
```

#### 任务 8.2：前端新增 Trace 状态

- `stores/chat.ts`：新增 `agentTrace: ref<AgentTraceStep[]>([])`
- `api/index.ts`：新增 `onAgentTrace` 处理器
- 新增 `AgentTracePanel.vue` 组件：可折叠的步骤列表

#### 任务 8.3：ChatWindow 集成

在 `ChatWindow.vue` 的 assistant 消息下方，新增可折叠的"查看推理过程"面板。

### 验收标准

- Deep 模式下看到推理步骤展示
- 面板可折叠/展开
- 不影响 default 模式
- 刷新后从 JSON 恢复 trace 数据

---

## 风险与控制

| 风险 | 等级 | 控制方式 |
|------|------|---------|
| DeepAgents API 不稳定 | 🔴 高 | 阶段 0 探针测试先行；锁定版本号；编写适配层隔离 |
| Anthropic tool calling 不兼容 | 🔴 高 | 阶段 0 优先验证；失败时有降级方案（回退到 OpenAI 兼容模式） |
| 流式事件行为差异 | 🟡 中 | `AgentStreamAdapter` 统一事件映射；阶段 7 测试覆盖 |
| 性能退化（简单问答走 Agent） | 🟡 中 | `default` 模式保留 LCEL 链，不走 DeepAgents |
| 依赖冲突 | 🟡 中 | 阶段 0 在虚拟环境中先行验证 |
| 旧测试回归 | 🟢 低 | 每个阶段完成后运行全量测试 |
| 前端适配 | 🟢 低 | SSE 协议兼容，阶段 8 为可选增强 |

---

## 验证方案

### 后端

- 阶段 0：探针测试全部通过
- 阶段 1-3：每个模块完成后运行 `pytest`
- 阶段 4-5：使用 curl 验证 SSE 事件顺序和内容
- 阶段 6：`grep` 确认无旧代码残留
- 阶段 7：全量 `pytest` 通过

### 端到端

- 启动后端和前端
- 新建对话，发送命中知识库的问题
- 验证 `default` 模式：流式 token、参考文件、done 事件
- 验证 `deep` 模式：agent_think/agent_observe 事件、最终回答
- 刷新页面确认对话恢复
- 测试 external 接口：免登录 SSE 流式
- 测试停止生成功能

### 回滚验证

```bash
git checkout master
pip install -r requirements.txt
# 确认后端启动正常
# 确认前端功能正常
```

---

## 文件变更总览

| 操作 | 文件 | 阶段 |
|------|------|------|
| ✨ 新增 | `backend/app/core/agent_tools.py` | 1 |
| ✨ 新增 | `backend/app/core/agent_builder.py` | 2 |
| ✨ 新增 | `backend/app/core/agent_stream.py` | 3 |
| ✨ 新增 | `backend/tests/test_deepagents_probe.py` | 0 |
| ✨ 新增 | `backend/tests/test_agent_tools.py` | 7 |
| ✨ 新增 | `backend/tests/test_agent_builder.py` | 7 |
| ✨ 新增 | `backend/tests/test_agent_stream.py` | 7 |
| 🔄 重构 | `backend/app/api/chat.py` | 4 |
| 🔄 重构 | `backend/app/api/external_chat.py` | 5 |
| 🔄 修改 | `backend/app/core/llm_factory.py` | 2 |
| 🔄 修改 | `backend/requirements.txt` | 0, 6 |
| 🔄 修改 | `backend/app/main.py` | 6 |
| 🔄 修改 | `CLAUDE.md` | 6 |
| 🔄 修改 | `docs/设计方案.md` | 6 |
| ❌ 删除 | `backend/app/core/chain_builder.py` | 6 |
| 🟡 可选 | `frontend/src/types/index.ts` | 8 |
| 🟡 可选 | `frontend/src/api/index.ts` | 8 |
| 🟡 可选 | `frontend/src/stores/chat.ts` | 8 |
| 🟡 可选 | `frontend/src/components/AgentTracePanel.vue` | 8 |

---

## 预估工作量

| 阶段 | 内容 | 预估时间 | 依赖 |
|------|------|---------|------|
| 0 | 环境准备与技术验证 | 1-2 天 | — |
| 1 | 拆出 `agent_tools.py` | 1 天 | 0 |
| 2 | 新增 `agent_builder.py` | 2 天 | 1 |
| 3 | 新增 `agent_stream.py` | 1.5 天 | 2 |
| 4 | 重构 `chat.py` | 1.5 天 | 3 |
| 5 | 重构 `external_chat.py` | 0.5 天 | 3 |
| 6 | 清理旧代码与依赖 | 0.5 天 | 4, 5 |
| 7 | 测试更新与验证 | 1.5 天 | 6 |
| 8 | 前端适配（可选） | 1 天 | 7 |
| **合计** | | **10.5-11.5 天** | |

---

## API 差异附录

*（阶段 0 已完成，2026-06-13）*

### 阶段 0 执行结果

**安装版本：**
```
deepagents            0.6.8
langchain             1.3.9
langchain-core        1.4.7
langchain-openai      1.3.0
langchain-anthropic   1.4.6
langchain-classic     1.0.8
langgraph             1.2.4
langgraph-prebuilt    1.1.0
```

**结构测试：18/18 通过**（含 1 个报告测试）

**LLM 测试：6 跳过**（无 API key 配置，预期行为）

**旧测试回归：53/54 通过**（1 个失败为预先存在的 LLM 配置问题，与升级无关）

### DeepAgents 与 LangChain AgentExecutor 关键差异

| 项目 | LangChain AgentExecutor | DeepAgents (0.6.8) |
|------|------------------------|---------------------|
| 创建方式 | `create_tool_calling_agent()` + `AgentExecutor()` | `create_deep_agent()` |
| 执行方式 | `executor.invoke()` 同步 | `agent.ainvoke()` 异步 |
| 流式方式 | 自定义回调 + 线程池 | `agent.astream_events()` 原生异步 |
| 消息格式 | `{"input": str, "chat_history": list}` | `{"messages": [dict或Message, ...]}` |
| 迭代限制 | `max_iterations` | `recursion_limit`（LangGraph 配置） |
| 中间件 | 无 | `FilesystemMiddleware`, `SubAgentMiddleware` 等 |
| middleware 默认 | N/A | **空元组 `()`** — 不强制启用任何中间件 ✓ |
| backend 默认 | N/A | **`None`** — 不强制启用文件系统 ✓ |
| 子代理 | 无 | `subagents` 参数 |
| model 参数 | ChatModel | `str \| BaseChatModel \| None` |
| tools 参数 | BaseTool 列表 | `Sequence[BaseTool \| Callable \| dict]` |
| system_prompt | ChatPromptTemplate | `str \| SystemMessage \| None` |

### 已验证项

- [x] ✓ `create_deep_agent()` 接受 `BaseChatModel`（ChatOpenAI/ChatAnthropic 兼容）
- [x] ✓ `create_deep_agent()` 接受 `BaseTool` 列表（`@tool` 装饰器兼容）
- [x] ✓ `@tool` 装饰器创建的 `StructuredTool` 可直接传入（新版 langchain-core 中通过 `.invoke()` 调用）
- [x] ✓ `system_prompt` 支持字符串
- [x] ✓ `middleware` 默认值为空元组 `()` — 无需显式关闭
- [x] ✓ `backend` 默认值为 `None` — 无需显式关闭
- [x] ✓ LangChain `HumanMessage`/`AIMessage` 对象兼容
- [x] ✓ dict 格式消息 `{"role": "user", "content": "..."}` 兼容
- [x] ✓ 现有 `format_history()` 函数输出与 DeepAgents 消息格式一致
- [x] ✓ `DeepAgentState` 包含 `messages` 字段
- [x] ✓ 所有依赖升级后无冲突（`pip check` 通过）
- [x] ✓ 旧测试无回归（53/54 通过，1 失败为预先存在）

### 待实际 LLM 验证项

- [ ] `ChatAnthropic` 在 DeepAgents 中的 tool calling 是否正常（需 ANTHROPIC_API_KEY）
- [ ] `astream_events` 的事件类型完整清单与 token 拼接方式（需 API key）
- [ ] `recursion_limit` 默认值及推荐值
- [ ] DeepAgents 对 `langchain-core` 的最低版本要求（当前 1.4.7 满足）

### 消息格式适配要点

DeepAgents 使用 `{"messages": [...]}` 格式，与当前 `chain_builder.format_history()` 的返回格式一致（`List[HumanMessage | AIMessage]`）。迁移时：

```python
# 当前格式（AgentExecutor）
chain.invoke({
    "input": message,           # str
    "chat_history": formatted,  # List[HumanMessage|AIMessage]
})

# DeepAgents 格式
agent.ainvoke({
    "messages": [               # 全部放入 messages
        SystemMessage(content=system_prompt),
        *formatted_history,
        HumanMessage(content=message),
    ]
})
```

### 流式事件结构

基于 `astream_events(version="v2")` 的事件结构：

```python
# on_chat_model_stream
{
    "event": "on_chat_model_stream",
    "data": {"chunk": AIMessageChunk(content="text", ...)},
    "metadata": {"langgraph_node": "agent", ...}
}

# on_tool_start
{
    "event": "on_tool_start",
    "name": "tool_name",
    "data": {"input": {...}},
}

# on_tool_end
{
    "event": "on_tool_end",
    "name": "tool_name",
    "data": {"output": "..."},
}
```