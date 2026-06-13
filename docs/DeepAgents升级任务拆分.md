# DeepAgents 升级任务拆分计划（修订版 v2）

## Context

当前项目已完成 LangChain 六阶段开发，实现了基于 `langchain-classic` 的 `AgentExecutor` 深度思考模式。

本计划的目标是将 LangChain Agent 体系全面升级为 DeepAgents（`deepagents`），采用官方推荐的 v3 协议 + `@langchain/vue` 前端 SDK 架构，而非自定义 SSE 映射。

## 架构变更

```
升级前（当前）                           升级后（v2 修订版）
┌──────────────┐                       ┌──────────────────┐
│  Vue3 前端    │                       │  Vue3 前端         │
│  fetchEvent   │                       │  useStream()      │ ← @langchain/vue
│  Source (SSE) │                       │  axios (CRUD)     │
└──────┬───────┘                       └───┬────────┬──────┘
       │ SSE                               │ v3协议  │ HTTP
┌──────┴───────┐                       ┌───┴────────┴──────┐
│  FastAPI      │                       │  Agent Server      │ ← langgraph dev
│  /api/chat/   │                       │  /runs/stream      │    (port 2024)
│  stream (SSE) │                       │  + FastAPI 自定义路由│
│  + CRUD/Auth  │                       │    /api/conversations│
└──────────────┘                       │    /api/auth         │
                                       │    /api/knowledge    │
                                       └─────────────────────┘
```

### 核心变化

| 维度 | 旧方案（v1 SSE映射） | 新方案（v2 官方协议） |
|------|---------------------|---------------------|
| 后端流式 | 自定义 `agent_stream.py` 映射层 | Agent Server 原生 v3 协议 |
| 传输协议 | 自定义 SSE 5 种事件 | Agent Server Protocol（content-block-delta 等） |
| 前端流式 | `fetchEventSource` + 手动解析 | `@langchain/vue` 的 `useStream()` |
| 子代理 | 不支持（无对应 SSE 事件） | `stream.subagents` + `SubagentCard` |
| 工具调用 | `agent_think`/`agent_observe` 文本事件 | `stream.tool_calls` 结构化投影 |
| 状态管理 | Pinia 手动管理 | `useStream()` 内置响应式状态 |
| 服务部署 | 单 FastAPI 进程 | FastAPI 自定义路由挂载到 Agent Server（单进程） |

### 为什么不再做 SSE 映射

1. **v3 协议是类型化投影**（`stream.messages`、`stream.tool_calls`、`stream.subagents`），不是简单的 token 流——SSE 无法表达这种结构
2. **`@langchain/vue` 已提供完整前端方案**——不需要自己实现流式解析、工具调用展示、子代理卡片
3. **避免重复造轮子**——Agent Server 自带持久化、checkpoint、线程管理
4. **长期可维护**——跟随 DeepAgents 官方升级，不需要维护私有协议

## 关键设计决策

- **采用 LangGraph Agent Server**：使用 `langgraph dev`（开发）和 `langgraph up`（生产部署）
- **FastAPI 作为自定义路由挂载**：现有的 CRUD/Auth/Admin 路由通过 `langgraph.json` 的 `http.app` 挂载
- **前端采用 `@langchain/vue`**：`useStream()` 处理流式消息，axios 处理 CRUD
- **对话持久化**：Agent Server 自带 checkpoint 持久化（开发模式用 SQLite），同时保留 `chat_manager.py` 用于元数据和兼容
- **安全边界不变**：知识库工具仍限制在 `KNOWLEDGE_PATH` 内

## 总体开发顺序

1. ✅ 环境准备与技术验证 — 已完成
2. ✅ 拆出 `agent_tools.py` — 已完成
3. ✅ 新增 `agent_builder.py` — 已完成
4. 🔄 新增 `agent_graph.py` + `langgraph.json` — Agent Server 配置与图导出
5. 🔄 前端接入 `@langchain/vue` — useStream 替换 fetchEventSource
6. 🔄 FastAPI 挂载为自定义路由 — 合并到 Agent Server
7. 🔄 外部接口适配 — external_chat 迁移
8. 🔄 清理旧代码、测试更新、部署配置

---

## 阶段 4：Agent Server 配置 + 图导出

### 目标

创建 Agent Server 所需的配置文件和图导出模块，使 `langgraph dev` 可以启动。

### 关键文件

- `backend/langgraph.json`（新增）
- `backend/app/agent_graph.py`（新增）
- `backend/app/api/chat.py`（标记废弃，流式逻辑移至 Agent Server）
- `backend/app/api/external_chat.py`（标记废弃）

### 任务

#### 任务 4.1：创建 `langgraph.json`

```json
{
  "dependencies": ["."],
  "graphs": {
    "answer-agent": "./backend/app/agent_graph.py:agent"
  },
  "env": ".env",
  "http": {
    "app": "./backend/app/main.py:app",
    "mount_prefix": "/api"
  }
}
```

说明：
- `graphs`：注册 DeepAgent 图
- `http.app`：将现有 FastAPI 应用作为自定义路由挂载
- `mount_prefix`：自定义路由前缀 `/api`

#### 任务 4.2：创建 `agent_graph.py` — 图导出模块

```python
# 导出编译好的 DeepAgent 图供 Agent Server 使用
from core.agent_builder import build_deep_agent, build_kb_agent, build_simple_agent

# Agent Server 通过 assistant_id 路由到不同图
# 需要根据 mode 参数创建不同的 agent
```

需要研究如何根据 `mode` 参数在 Agent Server 中切换不同图。

#### 任务 4.3：安装 langgraph-cli

```bash
pip install -U "langgraph-cli[inmem]"
```

#### 任务 4.4：验证 `langgraph dev` 能启动

- 启动 Agent Server（port 2024）
- 确认 FastAPI 自定义路由可访问（`/api/health` 等）
- 使用 curl 测试 `/runs/stream` 端点

### 验收标准

- `langgraph dev` 启动成功
- `/api/health` 返回正常
- `/runs/stream` 可接收请求并流式返回
- 知识库工具在 Agent 中可正常调用
- Agent Server 使用 SQLite checkpoint 持久化对话

---

## 阶段 5：前端接入 `@langchain/vue`

### 目标

用 `@langchain/vue` 的 `useStream()` 替换当前的 `fetchEventSource` + 手动 SSE 解析。

### 关键文件

- `frontend/package.json`（新增依赖）
- `frontend/src/api/index.ts`（简化：移除 SSE 相关，保留 CRUD）
- `frontend/src/stores/chat.ts`（重构：useStream 管理流式状态）
- `frontend/src/composables/useChatStream.ts`（新增）
- `frontend/src/components/ChatWindow.vue`（适配）
- `frontend/src/components/MessageBubble.vue`（适配）
- `frontend/src/components/SubagentCard.vue`（新增）

### 任务

#### 任务 5.1：安装前端依赖

```bash
cd frontend
npm install @langchain/vue @langchain/core
```

#### 任务 5.2：创建 `useChatStream.ts` composable

```typescript
import { useStream } from "@langchain/vue";

const AGENT_URL = "http://localhost:2024";

export function useChatStream() {
  const stream = useStream({
    apiUrl: AGENT_URL,
    assistantId: "answer-agent",
  });

  // stream.messages → 主消息流
  // stream.tool_calls → 工具调用流
  // stream.subagents → 子代理流
  // stream.submit() → 发送消息
  // stream.output → 最终状态

  return {
    stream,
    submit: (content: string) => {
      stream.submit({
        messages: [{ type: "human", content }],
      });
    },
  };
}
```

#### 任务 5.3：简化 `api/index.ts`

- 保留对话 CRUD（axios）：`getConversations`、`createConversation`、`deleteConversation`、`renameConversation`
- 保留 Auth API：`apiLogin`、`apiRegister`、`apiChangePassword`
- 保留 Admin API：`getModelConfig`、`updateModelConfig` 等
- 移除 `streamChat` 函数和 `StreamChatHandlers` 接口
- 移除 `@microsoft/fetch-event-source` 依赖

#### 任务 5.4：重构 `stores/chat.ts`

- 移除 `isStreaming`、`matchedKbs`、`selectedFiles`、`thinkingSteps`（useStream 内部管理）
- 移除 `sendMessage` 中的 fetchEventSource 逻辑
- 新增 `submitMessage` 调用 `stream.submit()`
- 对话 CRUD 逻辑保持不变

#### 任务 5.5：适配 `ChatWindow.vue` 和 `MessageBubble.vue`

- 消息从 `stream.messages` 获取（响应式）
- 工具调用从 `stream.tool_calls` 获取
- 消息渲染使用 `message.text` 迭代器

#### 任务 5.6：新增 `SubagentCard.vue`

```vue
<template>
  <div class="subagent-card" :class="{ expanded }">
    <div class="subagent-header" @click="toggle">
      <StatusIcon :status="subagent.status" />
      <span class="name">{{ subagent.name }}</span>
      <StatusBadge :status="subagent.status" />
    </div>
    <div v-if="expanded" class="subagent-content">
      <!-- 子代理的消息和工具调用 -->
    </div>
  </div>
</template>
```

### 验收标准

- 前端可正常加载对话列表
- 发送消息后 `stream.messages` 实时展示 token
- 工具调用以结构化方式展示（不再是文本）
- 子代理工作以卡片形式展示
- 停止生成可用
- 前端 TypeScript 构建通过

---

## 阶段 6：FastAPI 挂载为 Agent Server 自定义路由

### 目标

将现有 FastAPI 应用作为 Agent Server 的自定义路由，实现单进程部署。

### 关键文件

- `backend/langgraph.json`（修改）
- `backend/app/main.py`（修改：移除 chat streaming 端点，适配 Agent Server 环境）
- `backend/docker-compose.yml`（更新）

### 任务

#### 任务 6.1：修改 `main.py`

- 移除 `chat.router` 和 `external_chat.router` 的注册
- 保留 `conversations.router`、`knowledge_bases.router`、`auth.router`、`admin.router`
- 确保应用作为 Starlette app 可被 Agent Server 加载
- CORS 配置协调（Agent Server 自带 CORS）

#### 任务 6.2：配置 `langgraph.json` 挂载路径

确定自定义路由的前缀和 Agent Server 的交互方式。

#### 任务 6.3：更新 `docker-compose.yml`

- 开发环境：`langgraph dev`（单进程）
- 生产环境：`langgraph build` + Docker（或保留 docker-compose 双服务架构）

### 验收标准

- `langgraph dev` 启动后 `/api/health` 可访问
- `/api/conversations` CRUD 正常
- `/api/auth/login` 正常
- Agent Server `/runs/stream` 正常
- 前端同时使用两个端点（Agent Server + FastAPI）正常工作

---

## 阶段 7：外部接口适配

### 目标

保留免登录外部调用能力，在新架构下实现。

### 关键文件

- `backend/app/api/external_chat.py`（重写或创建新的 agent graph）

### 任务

#### 任务 7.1：确定外部接口方案

选项：
- **方案 A**：在 Agent Server 中注册第二个 assistant（无需认证），前端直接调用
- **方案 B**：在 FastAPI 自定义路由中添加代理端点，转发到 Agent Server
- **方案 C**：在 FastAPI 中直接调用 `agent.astream_events()` 并映射为当前 SSE 协议（仅对外部接口保留 SSE）

推荐方案 A（简单且一致）。

### 验收标准

- 外部接口可正常流式问答
- 无需认证
- 不持久化对话

---

## 阶段 8：清理旧代码、测试更新、部署配置

### 目标

移除所有 langchain-classic 旧代码，更新测试，完成部署文档。

### 关键文件

- `backend/app/core/chain_builder.py`（删除）
- `backend/app/api/chat.py`（删除或标记废弃）
- `backend/requirements.txt`（移除 langchain-classic）
- `backend/tests/`（更新）
- `docker-compose.yml`（更新）
- `CLAUDE.md`、`README.md`、`DEPLOYMENT.md`（更新）

### 任务

#### 任务 8.1：清理旧代码

- 删除 `chain_builder.py`
- 删除 `chat.py` 中的 SSE 流式逻辑（如仍保留端点则标记废弃）
- 从 `requirements.txt` 移除 `langchain-classic`
- 搜索并移除所有 `AgentExecutor`、`create_tool_calling_agent` 引用

#### 任务 8.2：更新测试

- 移除依赖 `chain_builder` 的测试
- 新增 `test_agent_graph.py`（Agent Server 图导出）
- 更新 `test_deepagents_probe.py`

#### 任务 8.3：更新部署文档

- `CLAUDE.md`：更新架构描述和启动命令
- `DEPLOYMENT.md`：更新为 langgraph dev/up 方式
- `README.md`：更新技术栈

### 验收标准

- `grep -r "langchain_classic" backend/` 无结果
- `grep -r "AgentExecutor" backend/` 无结果
- 全量测试通过
- `langgraph dev` 一键启动
- 前端 + 后端联调通过
- Docker 部署验证通过

---

## 文件变更总览（修订版）

| 操作 | 文件 | 阶段 |
|------|------|------|
| ✨ 新增 | `backend/app/agent_graph.py` | 4 |
| ✨ 新增 | `backend/langgraph.json` | 4 |
| ✨ 新增 | `frontend/src/composables/useChatStream.ts` | 5 |
| ✨ 新增 | `frontend/src/components/SubagentCard.vue` | 5 |
| 🔄 重构 | `frontend/src/api/index.ts` | 5 |
| 🔄 重构 | `frontend/src/stores/chat.ts` | 5 |
| 🔄 重构 | `frontend/src/components/ChatWindow.vue` | 5 |
| 🔄 重构 | `frontend/src/components/MessageBubble.vue` | 5 |
| 🔄 修改 | `backend/app/main.py` | 6 |
| 🔄 修改 | `frontend/package.json` | 5 |
| 🔄 修改 | `docker-compose.yml` | 8 |
| 🔄 修改 | `CLAUDE.md`、`README.md`、`DEPLOYMENT.md` | 8 |
| ❌ 删除 | `backend/app/core/chain_builder.py` | 8 |
| ❌ 删除 | `backend/app/api/chat.py`（流式逻辑） | 8 |
| ❌ 删除 | `backend/app/api/external_chat.py`（流式逻辑） | 8 |
| ❌ 移除 | `langchain-classic` 依赖 | 8 |
| ❌ 移除 | `@microsoft/fetch-event-source` 依赖 | 5 |
| ✅ 保留 | `backend/app/core/agent_tools.py` | — |
| ✅ 保留 | `backend/app/core/agent_builder.py` | — |
| ✅ 保留 | 其余所有未列出的文件 | — |

---

## 预估工作量（修订版）

| 阶段 | 内容 | 预估时间 | 状态 |
|------|------|---------|------|
| 0 | 环境准备与技术验证 | 1 天 | ✅ 已完成 |
| 1 | 拆出 `agent_tools.py` | 1 天 | ✅ 已完成 |
| 2 | 新增 `agent_builder.py` | 1 天 | ✅ 已完成 |
| 3 | ~~agent_stream.py~~ | — | ❌ 取消（不需要 SSE 映射层） |
| 4 | Agent Server 配置 + 图导出 | 2 天 | 🔄 待开始 |
| 5 | 前端接入 `@langchain/vue` | 2-3 天 | 🔄 待开始 |
| 6 | FastAPI 挂载为自定义路由 | 1 天 | 🔄 待开始 |
| 7 | 外部接口适配 | 0.5 天 | 🔄 待开始 |
| 8 | 清理、测试、部署 | 1.5 天 | 🔄 待开始 |
| **合计** | | **9-10.5 天** | |

---

## 风险与控制（修订版）

| 风险 | 等级 | 控制方式 |
|------|------|---------|
| Agent Server 自定义路由不兼容现有 FastAPI 中间件 | 🔴 高 | 阶段 6 先行验证，必要时退回到双服务架构 |
| `@langchain/vue` 与现有 Vue3 组件集成复杂 | 🟡 中 | 阶段 5 渐进替换，保留旧组件做 A/B 切换 |
| Agent Server 持久化与现有 JSON 对话不兼容 | 🟡 中 | 保留 `chat_manager.py` 做元数据桥接 |
| 外部接口（免登录）在 Agent Server 中实现困难 | 🟡 中 | 注册第二个 assistant 或保留 FastAPI 代理端点 |
| `langgraph dev` 在生产环境的替代方案 | 🟢 低 | `langgraph up` 生成 Docker 镜像，配合 docker-compose |