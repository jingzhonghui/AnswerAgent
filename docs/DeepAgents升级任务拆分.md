# DeepAgents 升级任务拆分计划（修订版 v3）

## Context

当前项目已完成 LangChain 六阶段开发，实现了基于 `langchain-classic` 的 `AgentExecutor` 深度思考模式。

本计划的目标是将 LangChain Agent 体系升级为 DeepAgents（`deepagents`），**保持 FastAPI + SSE 架构不变**，仅替换底层 Agent 引擎。

## 架构变更

```
升级前（当前）                           升级后（v3 修订版）
┌──────────────┐                       ┌──────────────┐
│  Vue3 前端    │                       │  Vue3 前端     │  ← 不变
│  fetchEvent   │                       │  fetchEvent    │
│  Source (SSE) │                       │  Source (SSE)  │
└──────┬───────┘                       └──────┬────────┘
       │ SSE 5种事件                          │ SSE 5种事件（不变）
┌──────┴───────┐                       ┌──────┴────────┐
│  FastAPI      │                       │  FastAPI       │  ← 不变
│  /api/chat/   │                       │  /api/chat/    │
│  stream (SSE) │                       │  stream (SSE)  │
│  + CRUD/Auth  │                       │  + CRUD/Auth   │
└──────┬───────┘                       └──────┬────────┘
       │                                      │
┌──────┴───────┐                       ┌──────┴────────┐
│ AgentExecutor │  ← langchain-classic  │ create_deep_  │  ← deepagents
│ + 线程池      │                       │ agent()       │
│ + 回调推队列  │                       │ + astream_    │
└──────────────┘                       │ events(v3)    │
                                       └──────────────┘
```

### 核心变化

| 维度 | 旧方案 | 新方案（v3） |
|------|--------|-------------|
| Agent 引擎 | `AgentExecutor` + 线程池 | `create_deep_agent()` + `astream_events(v3)` |
| 流式消费 | 回调 → asyncio.Queue 桥接 | v3 原生异步流，无需线程池 |
| 中间步骤 | `on_agent_action` / `on_tool_end` 回调 | `stream.tool_calls` / `stream.messages` 结构化投影 |
| 传输协议 | FastAPI SSE（不变） | FastAPI SSE（不变） |
| 前端 | `fetchEventSource`（不变） | `fetchEventSource`（不变） |
| 部署 | `python main.py`（不变） | `python main.py`（不变） |

### 为什么不需要 langgraph dev / Agent Server / @langchain/vue

1. **`deepagents` 是 Python 库**，`create_deep_agent()` 返回普通 Python 对象，直接在 FastAPI 里调用即可
2. **`langgraph dev` 是部署平台**（类比 Vercel），给 SaaS 场景用的——有 Redis、gRPC、分布式运行时。单机 FastAPI 不需要
3. **`@langchain/vue` 的 `useStream()` 连接的是 Agent Server**，不是自定义 FastAPI。没有 Agent Server 就不能用它
4. **SSE 映射是自部署 FastAPI 场景的标准做法**——`astream_events(v3)` 提供结构化事件，映射为 SSE 发给前端，这是最直接的路径

**一句话：`create_deep_agent()` → `astream_events(v3)` → 映射 SSE → 前端不变。**

## 关键设计决策

- **保持 FastAPI**：不做 Agent Server 迁移，不引入 `langgraph dev`
- **保持 SSE 协议不变**：5 种事件（`kb_matched`、`files_selected`、`token`、`done`、`error`）+ 深度思考事件（`agent_think`、`agent_observe`）
- **前端代码零改动**：不引入 `@langchain/vue`，现有 `fetchEventSource` 继续工作
- **引擎替换**：`AgentExecutor` + 线程池 + 回调 → `create_deep_agent()` + `astream_events(v3)`
- **对话持久化不变**：继续使用 `chat_manager.py` JSON 文件存储

## 总体开发顺序

1. ✅ 环境准备与技术验证 — 已完成
2. ✅ 拆出 `agent_tools.py` — 已完成
3. ✅ 新增 `agent_builder.py` — 已完成
4. ✅ `chat.py` 用 `astream_events(v3)` 替代 `AgentExecutor` — 已完成
5. ✅ 外部接口适配 — `external_chat.py` 同步迁移
6. ✅ 清理旧代码、测试更新、部署文档

---

## 阶段 3：chat.py 用 astream_events(v3) 替代 AgentExecutor

### 目标

重写 `chat.py` 的 `_stream_deep()` 和 `_stream_default()`，统一使用 `agent_builder` 的 DeepAgent + `astream_events(v3)`。

### 关键变更

```
旧：                            新：
build_deep_chain(context)      build_deep_agent()
  → AgentExecutor                 → agent.astream_events(
  → 线程池 run_in_executor             {"messages": [...]},
  → 回调 → asyncio.Queue             version="v3"
  → 主循环轮询队列                  )
                                → async for event in stream:
                                    event["event"] 分发
```

### 任务

#### 任务 3.1：统一流式入口

将 `_stream_default()` 和 `_stream_deep()` 合并为一个统一的流式生成器，通过 `agent_builder` 构建不同的 agent，都用 `astream_events(v3)` 消费：

```
mode=default → build_simple_agent() 或 build_kb_agent(context)
mode=deep    → build_deep_agent()
```

#### 任务 3.2：v3 事件 → SSE 事件映射

```python
# astream_events(v3) 事件类型 → SSE 事件
"chat_model"   → stream.messages → token（逐 token）
"on_tool_start" → agent_think    → {step, tool, tool_input}
"on_tool_end"   → agent_observe  → {step, result}
"chain_end"     → done           → {message_id}
```

#### 任务 3.3：移除旧代码

- 删除 `_DeepThinkingCallback` 类
- 删除 `_clean_thought()` 函数
- 删除 `SENTINEL` 常量
- 删除 `run_in_executor` 线程池模式
- 移除 `from core.chain_builder import ...`（改用 `from core.agent_builder import ...`）
- 移除 `from langchain_core.callbacks import ...`
- 移除 `from langchain_core.agents import ...`

### 验收标准

- `mode=default` 流式问答正常（token 逐字推送）
- `mode=deep` 深度思考正常（agent_think / agent_observe / token 事件）
- 知识库路由 + 文件选取流程不变
- 对话持久化不变
- 停止生成可用
- 无线程池、无 `asyncio.Queue`、无 `SENTINEL`

---

## 阶段 4：外部接口适配

### 目标

`external_chat.py` 同步迁移到 DeepAgents，保持免登录外部调用能力。

### 关键文件

- `backend/app/api/external_chat.py`

### 任务

在 FastAPI 自定义路由中添加端点，使用 `agent_builder` 创建 agent，通过 `astream_events(v3)` 映射为现有 SSE 协议。

### 验收标准

- 外部接口可正常流式问答
- 无需认证
- 不持久化对话

---

## 阶段 5：清理旧代码、测试更新、部署配置

### 目标

移除所有 langchain-classic 旧代码，更新测试，更新文档。

### 关键文件

- `backend/app/core/chain_builder.py`（删除）
- `backend/requirements.txt`（移除 langchain-classic，如果有）
- `backend/tests/`（更新）
- `CLAUDE.md`、`README.md`（更新架构描述）

### 任务

#### 任务 5.1：清理旧代码

- 删除 `chain_builder.py`
- 搜索并移除所有 `AgentExecutor`、`create_tool_calling_agent`、`create_react_agent` 引用

#### 任务 5.2：更新测试

- 移除依赖 `chain_builder` 的测试
- 新增 `test_agent_chat.py`（chat.py 的 SSE 流式测试）
- 更新 `test_deepagents_probe.py`

#### 任务 5.3：更新文档

- `CLAUDE.md`：更新架构描述和启动命令
- `README.md`：更新技术栈

### 验收标准

- `grep -r "langchain_classic" backend/` 无结果
- `grep -r "AgentExecutor" backend/` 无结果
- 全量测试通过
- `python main.py` 一键启动
- 前端 + 后端联调通过

---

## 文件变更总览（修订版 v3）

| 操作 | 文件 | 阶段 |
|------|------|------|
| 🔄 重构 | `backend/app/api/chat.py` | 3 |
| 🔄 重构 | `backend/app/api/external_chat.py` | 4 |
| ❌ 删除 | `backend/app/core/chain_builder.py` | 5 |
| 🔄 修改 | `backend/tests/` | 5 |
| 🔄 修改 | `CLAUDE.md`、`README.md` | 5 |
| ✅ 保留 | `backend/app/core/agent_tools.py` | — |
| ✅ 保留 | `backend/app/core/agent_builder.py` | — |
| ✅ 保留 | `frontend/`（零改动） | — |
| ✅ 保留 | 其余所有未列出的文件 | — |

**与 v2 的关键差异：**
- ❌ 不需要 `agent_graph.py`
- ❌ 不需要 `langgraph.json`
- ❌ 不需要 `langgraph-cli`
- ❌ 不需要 `@langchain/vue`
- ❌ 不需要 `useChatStream.ts`
- ❌ 不需要 `SubagentCard.vue`
- ❌ 不需要修改 `main.py`
- ❌ 不需要修改前端任何代码

---

## 预估工作量（修订版 v3）

| 阶段 | 内容 | 预估时间 | 状态 |
|------|------|---------|------|
| 0 | 环境准备与技术验证 | 1 天 | ✅ 已完成 |
| 1 | 拆出 `agent_tools.py` | 1 天 | ✅ 已完成 |
| 2 | 新增 `agent_builder.py` | 1 天 | ✅ 已完成 |
| 3 | chat.py 用 astream_events(v3) 替代 AgentExecutor | 1-2 天 | ✅ 已完成 |
| 4 | 外部接口适配 | 0.5 天 | ✅ 已完成 |
| 5 | 清理、测试、部署 | 1 天 | ✅ 已完成 |
| **合计** | | **5.5-6.5 天** | |

## 风险与控制（修订版 v3）

| 风险 | 等级 | 控制方式 |
|------|------|---------|
| v3 事件结构复杂，映射 SSE 容易遗漏 | 🟡 中 | 先写测试用例覆盖所有事件类型 |
| `build_deep_agent()` 行为与旧 `AgentExecutor` 有差异 | 🟡 中 | A/B 对比测试，确保 tool calling 行为一致 |
| LLM API key 缺失导致集成测试无法跑 | 🟢 低 | mock LLM 或 skipif 标记 |