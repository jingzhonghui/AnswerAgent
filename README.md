# AnswerAgent

**基于本地知识库的问答智能体**

AnswerAgent 是一个基于本地文件目录的问答系统。后端使用 Python + FastAPI 和 DeepAgents，前端使用 Vue 3 + TypeScript。通过检索本地知识库中的文件内容，结合 LLM（OpenAI / Anthropic）生成回答。

## 核心特性

- **基于文件目录的知识库** — 无需向量数据库，知识就是 Markdown 和源码文件
- **两阶段检索** — 关键词粗筛（jieba）+ LLM 精读决策，零 Embedding 依赖
- **多知识库路由** — 自动匹配用户问题到最相关的知识库，结果可合并
- **SSE 流式输出** — 前端实时展示 LLM token 生成过程
- **深度思考模式** — DeepAgents ReAct Agent，可观察推理链和工具调用
- **JWT 认证系统** — 用户注册/登录，管理员权限隔离
- **管理后台** — 模型配置热更新、用户管理、会话管理、知识库生成工作流
- **知识库自动生成** — 从代码仓库/文档仓库自动生成结构化知识库文档
- **多对话管理** — 新建、重命名、删除、Markdown 导出
- **亮色 / 暗色双主题** — 偏好持久化到 localStorage
- **Docker 部署** — 双容器编排，内置 skills 自动同步

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + uvicorn |
| LLM 框架 | LangChain + DeepAgents（`create_deep_agent` + `astream_events(v3)`） |
| LLM 提供商 | OpenAI / Anthropic 兼容 API |
| 流式协议 | SSE（POST + sse-starlette） |
| 中文分词 | jieba |
| 数据库 | SQLite（aiosqlite）— 用户/对话元数据/配置/工作流 |
| 认证 | JWT + bcrypt |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| Markdown 渲染 | markdown-it + highlight.js |
| 数据存储 | SQLite + JSON 文件双存储 |

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

# 启动服务（首次启动后通过管理后台 /admin 配置 LLM API key）
python -m app.main
```

服务默认启动在 `http://localhost:8765`，可通过 `http://localhost:8765/api/health` 验证。

### 2. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端默认启动在 `http://localhost:5173`，开发模式下 `/api` 请求会自动代理到后端。

### 3. 首次使用

1. 打开 `http://localhost:5173`，注册一个账号
2. 默认管理员账号：`admin` / `admin123`
3. 管理员登录后访问 `/admin` 进入管理后台，配置 LLM API key
4. 返回聊天页面，新建对话开始提问

### 4. Docker 部署

```bash
# 构建并启动
docker compose build
docker compose up -d

# 验证
curl http://localhost:8765/api/health
```

详见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 配置说明

所有配置通过管理后台（`/admin` → 模型配置）管理，存储在 SQLite 数据库 `model_config` 表中，支持热更新（`knowledge_path`、`data_path`、`jwt_*` 等需重启生效）。

首次启动后请登录管理后台配置以下必需项：

| 配置项 | 说明 |
|--------|------|
| `llm_provider` | LLM 提供商：`openai` 或 `anthropic` |
| `api_key` | API 密钥 |
| `base_url` | API 地址（OpenAI 兼容 API 如 DeepSeek 需填写） |
| `model` | 模型名称，默认 `gpt-4o` |
| `deep_model_enabled` | 是否启用深度思考模式 |

> **提示**：`backend/.env.example` 仅供列示配置项参考，程序不再读取该文件。如需在首次启动时通过环境变量注入初始值，可设置同名 OS 环境变量（如 `API_KEY=xxx`），启动后仍会以数据库配置为准。

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

### 知识库自动生成

管理后台提供"知识库生成"工作流，支持从以下来源自动生成结构化知识库：

- **本地路径** — 服务器上的代码/文档目录
- **Git 仓库** — 自动 clone 并分析
- **压缩包上传** — 上传 zip/tar.gz（最大 500MB）

工作流会自动识别仓库类型（代码/文档），使用 LLM 分析源码结构，生成索引文件和模块设计文档。

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

`mode` 可选值：
- `"default"` — 标准问答模式（知识库上下文注入）
- `"deep"` — 深度思考模式（ReAct Agent，可观察推理链和工具调用）

### 事件清单

| 事件名 | 触发时机 | data 字段 |
|---|---|---|
| `kb_matched` | 路由完成 | `kb_names: string[]` |
| `files_selected` | 选完一个知识库的文件 | `kb: string`, `files: string[]` |
| `token` | LLM 每生成一个 token | `content: string` |
| `agent_think` | 深度思考推理步骤 | `step`, `thought`, `tool`, `tool_input` |
| `agent_observe` | 工具执行结果 | `step`, `result` |
| `done` | 流式完成 | `message_id: string` |
| `error` | 任意阶段异常 | `message: string` |

## 项目结构

```
AnswerAgent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py              # 认证（注册/登录/修改密码）
│   │   │   ├── chat.py              # SSE 流式问答
│   │   │   ├── external_chat.py     # 免登录外部问答
│   │   │   ├── conversations.py     # 对话 CRUD + 导出
│   │   │   ├── knowledge_bases.py   # 知识库列表
│   │   │   ├── admin.py             # 管理后台
│   │   │   ├── workflow.py          # 知识库生成工作流
│   │   │   └── public.py            # 公开配置
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings
│   │   │   ├── database.py          # SQLite 初始化 + 迁移
│   │   │   ├── deps.py              # JWT 认证依赖
│   │   │   ├── security.py          # bcrypt + JWT
│   │   │   ├── llm_factory.py       # LLM 工厂
│   │   │   ├── model_config.py      # 运行时配置服务
│   │   │   ├── kb_router.py         # 知识库路由
│   │   │   ├── file_loader.py       # 两阶段文件选取
│   │   │   ├── agent_builder.py     # DeepAgents 构建工厂
│   │   │   ├── agent_tools.py       # 知识库工具
│   │   │   ├── chat_manager.py      # 对话持久化
│   │   │   ├── skill_loader.py      # Skills 加载器
│   │   │   ├── source_tools.py      # 源码探索工具
│   │   │   ├── workflow_engine.py   # 工作流引擎
│   │   │   ├── workflow_analyzer.py # 工作流分析
│   │   │   ├── workflow_executor.py # 工作流执行
│   │   │   └── workflow_preprocess.py # 工作流预处理
│   │   ├── models/
│   │   │   └── schemas.py           # Pydantic 模型
│   │   └── main.py                  # FastAPI 入口
│   ├── skills/                      # 内置 Skills（kb-generator）
│   ├── knowledge/                   # 知识库目录
│   ├── data/                        # 运行时数据（answeragent.db + conversations/）
│   ├── tests/                       # 测试
│   ├── Dockerfile
│   ├── docker-entrypoint.sh
│   ├── .env.example          # 配置项参考（程序不再读取）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/index.ts
│   │   ├── components/
│   │   │   ├── ChatWindow.vue
│   │   │   ├── ConversationSidebar.vue
│   │   │   ├── InputBar.vue
│   │   │   └── admin/
│   │   │       ├── ModelConfig.vue
│   │   │       ├── UserManagement.vue
│   │   │       ├── ConversationManagement.vue
│   │   │       └── KbWorkflow.vue
│   │   ├── stores/
│   │   ├── router/
│   │   ├── views/
│   │   ├── types/index.ts
│   │   └── main.ts
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docs/
│   ├── API接口文档.md
│   ├── 外部接口对接文档.md
│   ├── 设计方案.md
│   └── 开发任务拆分.md
├── docker-compose.yml
├── DEPLOYMENT.md
├── AGENTS.md
└── README.md
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
- **密码安全**：所有密码使用 bcrypt 哈希存储，JWT 密钥可配置。

## License

MIT