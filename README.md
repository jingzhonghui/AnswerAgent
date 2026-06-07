# AnswerAgent

**基于本地知识库的问答智能体**

AnswerAgent 是一个基于本地文件目录的问答系统。后端使用 Python + FastAPI 和 LangChain，前端使用 Vue 3 + TypeScript。通过检索本地知识库中的文件内容，结合 LLM（OpenAI / Anthropic）生成回答。

## 核心特性

- **基于文件目录的知识库** — 无需向量数据库，知识就是 Markdown 和源码文件
- **两阶段检索** — 关键词粗筛 + LLM 精读决策，零 Embedding 依赖
- **多知识库路由** — 自动匹配用户问题到最相关的知识库，结果可合并
- **SSE 流式输出** — 前端实时展示 LLM token 生成过程
- **多对话管理** — 新建、重命名、删除、按时间分组
- **亮色 / 暗色双主题** — 偏好持久化到 localStorage
- **JSON 文件持久化** — 零数据库依赖，每个对话一个独立 JSON 文件

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + uvicorn |
| LLM 框架 | LangChain（LCEL） |
| LLM 提供商 | OpenAI / Anthropic 兼容 API |
| 流式协议 | SSE（POST + sse-starlette） |
| 中文分词 | jieba |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| Markdown 渲染 | markdown-it + highlight.js |
| 数据存储 | JSON 文件 |

## 快速开始

### 前置条件

- Python 3.10+
- Node.js 18+
- 一个 LLM API key（OpenAI 兼容或 Anthropic）

### 1. 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API key（见下方配置说明）

# 启动服务
python -m app.main
```

服务默认启动在 `http://localhost:8000`，可通过 `http://localhost:8000/api/health` 验证。

### 2. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端默认启动在 `http://localhost:5173`，开发模式下 `/api` 请求会自动代理到后端。

### 3. 验证

打开 `http://localhost:5173`，新建对话，发送以下示例问题：

```
AnswerAgent 的 SSE 协议有哪些事件类型？
```

如果知识库命中，会看到 `kb_matched` 和 `files_selected` 标签，然后 LLM 逐步输出回答。

## 配置说明

后端配置通过 `backend/.env` 文件管理：

```ini
# LLM 提供商选择：openai | anthropic
LLM_PROVIDER=openai

# OpenAI 兼容配置（支持 DeepSeek、通义千问等）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-v4-flash

# Anthropic 配置
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_BASE_URL=
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# 路径配置
KNOWLEDGE_PATH=./knowledge
DATA_PATH=./data/conversations

# 对话历史保留轮数（每轮 = 1 问 1 答），默认 10
HISTORY_WINDOW=10
```

**注意**：使用 OpenAI 兼容 API 时（如 DeepSeek、通义千问），设置 `OPENAI_BASE_URL` 为对应服务地址，`LLM_PROVIDER=openai`。

## 知识库结构

知识库位于 `backend/knowledge/` 下，每个知识库是一个独立目录：

```
backend/knowledge/
└── {知识库名称}/
    ├── 索引.md           # 可选，提供知识库描述供 LLM 路由
    ├── overview.md       # 知识文档（Markdown）
    ├── architecture.md
    └── src/              # 可选，源码示例
        └── example.py
```

### 索引文件

`索引.md` 是知识库的"目录"，包含文件清单和简要描述。`kb_router` 和 `file_loader` 会优先读取它来提高匹配精度。

### 支持的文件类型

Markdown（`.md`、`.markdown`）、纯文本（`.txt`）、常见源码文件（`.py`、`.ts`、`.vue`、`.js`、`.java` 等）、配置文件（`.json`、`.yaml`、`.toml` 等）。

### 内置示例：AnswerAgent 知识库

项目内置了一个 `AnswerAgent` 知识库，包含项目自身的设计文档，方便你开箱体验。以下问题可以稳定命中：

| 示例问题 | 预期命中知识库 | 参考文件 |
|---|---|---|
| "AnswerAgent 使用什么技术栈？" | AnswerAgent | overview.md |
| "SSE 协议有哪些事件类型？" | AnswerAgent | sse-protocol.md |
| "知识库如何进行文件检索？" | AnswerAgent | knowledge-base-strategy.md |
| "对话数据如何存储？" | AnswerAgent | conversation-storage.md |
| "项目后端有哪些模块？" | AnswerAgent | architecture.md |

## SSE 流式协议

流式问答接口 `POST /api/chat/stream`。请求体为 JSON：

```json
{
  "conversation_id": "uuid",
  "message": "用户问题",
  "mode": "default"
}
```

响应为 SSE 事件流，每个事件包含 `event` 和 `data` 字段，`data` 为 JSON 字符串：

```
event: kb_matched
data: {"kb_names": ["AnswerAgent"]}

event: files_selected
data: {"kb": "AnswerAgent", "files": ["overview.md", "architecture.md"]}

event: token
data: {"content": "根据"}

event: token
data: {"content": "参考文件"}

event: done
data: {"message_id": "uuid"}
```

### 事件清单

| 事件名 | 触发时机 | data 字段 |
|---|---|---|
| `kb_matched` | 路由完成 | `kb_names: string[]` — 匹配的知识库名称 |
| `files_selected` | 选完一个知识库的文件 | `kb: string`, `files: string[]` |
| `token` | LLM 每生成一个 token | `content: string` |
| `done` | 流式完成 | `message_id: string` |
| `error` | 任意阶段异常 | `message: string` |

### 为什么用 POST + SSE 而不是原生 EventSource？

原生浏览器 `EventSource` 只支持 GET 请求，无法发送 JSON body。本接口发送消息会创建/更新对话（有副作用），语义上应为 POST。因此前端使用 `@microsoft/fetch-event-source` 来消费 POST SSE 响应。

### 为什么用 SSE 而非 WebSocket？

SSE 是单向推送（服务器→客户端），原生支持，无需额外鉴权握手协议。WebSocket 适合双向实时通信，本项目不需要。

## 项目结构

```
AnswerAgent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── chat.py              # SSE 流式问答接口
│   │   │   ├── conversations.py     # 对话 CRUD 接口
│   │   │   └── knowledge_bases.py   # 知识库列表接口
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings 配置
│   │   │   ├── llm_factory.py       # LLM 工厂（OpenAI/Anthropic）
│   │   │   ├── kb_router.py         # 知识库匹配路由
│   │   │   ├── file_loader.py       # 两阶段文件选取
│   │   │   ├── chain_builder.py     # LCEL 问答链
│   │   │   └── chat_manager.py      # 对话 JSON 持久化
│   │   ├── models/
│   │   │   └── schemas.py           # Pydantic 模型
│   │   └── main.py                  # FastAPI 入口
│   ├── knowledge/                   # 知识库目录
│   │   └── AnswerAgent/             # 内置示例知识库
│   ├── data/                        # 运行时数据（git ignored）
│   │   └── conversations/
│   ├── tests/                       # 测试
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api/index.ts             # HTTP + SSE 封装
    │   ├── components/
    │   │   ├── ChatWindow.vue       # 聊天窗口
    │   │   ├── ConversationSidebar.vue  # 侧边栏
    │   │   └── InputBar.vue         # 输入栏
    │   ├── stores/chat.ts           # Pinia 状态管理
    │   ├── types/index.ts           # TypeScript 类型定义
    │   ├── App.vue                  # 根组件 + 主题管理
    │   └── main.ts
    ├── index.html
    ├── package.json
    └── vite.config.ts
```

## 开发命令

### 后端

```bash
cd backend

# 运行测试
python -m pytest tests/ -v

# 启动服务
python -m app.main
```

### 前端

```bash
cd frontend

# TypeScript 类型检查
npx vue-tsc --noEmit

# 构建生产版本
npm run build

# 开发服务器（热更新）
npm run dev
```

## 风险与安全

- **路径穿越防护**：所有知识库文件读取和对话文件操作都经过 `resolve()` → `relative_to()` 校验，禁止逃出限定目录。
- **原子写入**：对话文件使用临时文件 + `os.replace()`，避免写入中断导致数据损坏。
- **文件类型白名单**：知识库仅读取白名单后缀文件（Markdown、源码、配置文件），忽略二进制文件。
- **内容上限**：单文件 20KB、单知识库 60KB 字符上限，防止上下文爆炸。

## License

MIT
