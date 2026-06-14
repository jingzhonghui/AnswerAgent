# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

代码已全部实现，**不是**设计阶段。后端使用 FastAPI + SQLite + DeepAgents，前端使用 Vue 3 + TypeScript + Vite。完整的管理后台、JWT 认证、知识库生成工作流等功能均已落地。

## 常用命令

### 后端

```bash
cd backend
pip install -r requirements.txt
python -m app.main      # 监听 0.0.0.0:8765（首次启动后通过 /admin 配置 API key）
```

### 前端

```bash
cd frontend
npm install
npm run dev            # 监听 localhost:5173，/api 代理到 :8765
```

### 测试

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

### 构建

```bash
cd frontend
npm run build    # vue-tsc --noEmit + vite build
```

### Docker

```bash
docker compose build
docker compose up -d
```

## 高层架构

AnswerAgent 是一个基于本地文件目录的问答智能体：后端从本地知识库中检索相关文件内容，再通过 DeepAgents（`create_deep_agent()` + `astream_events(v3)`）调用 LLM 生成回答；前端通过 SSE 展示流式输出。

### 后端目录

`backend/app/`：

- `api/`：FastAPI 路由层
  - `auth.py` — 注册、登录、修改密码（JWT + bcrypt）
  - `chat.py` — SSE 流式问答（default / deep 两种模式）
  - `external_chat.py` — 免登录外部流式问答
  - `conversations.py` — 对话 CRUD + Markdown 导出
  - `knowledge_bases.py` — 知识库列表
  - `admin.py` — 管理后台（模型配置、用户管理、会话管理）
  - `workflow.py` — 知识库生成工作流（启动/暂停/恢复/删除/日志 SSE）
  - `public.py` — 公开配置（deep_model_enabled 开关）
- `core/`：
  - `config.py` — Pydantic Settings，配置已迁移到 SQLite `model_config` 表
  - `database.py` — SQLite 初始化 + 迁移（users / conversations / model_config / kb_workflow_tasks）
  - `deps.py` — JWT 认证依赖（get_current_user / get_current_admin_user）
  - `security.py` — bcrypt 密码哈希 + JWT 创建/解码
  - `llm_factory.py` — LLM 工厂，支持 OpenAI 与 Anthropic，独立 deep_* 配置
  - `model_config.py` — 运行时配置服务，内存缓存 + SQLite 持久化，支持热更新
  - `kb_router.py` — 扫描知识库，LLM 判断问题匹配哪些知识库
  - `file_loader.py` — 两阶段文件选取：关键词粗筛 + LLM 精读
  - `agent_builder.py` — DeepAgents 构建工厂（simple / kb / deep 三种 Agent）
  - `agent_tools.py` — 知识库工具（list_knowledge_bases / search_kb_files / read_kb_file）
  - `chat_manager.py` — 对话持久化：SQLite 元数据 + JSON 文件消息内容
  - `skill_loader.py` — 扫描 `skills/` 目录，加载 SKILL.md 为 DeepAgents 虚拟文件
  - `source_tools.py` — 工作流源码探索工具（list / read / search）
  - `workflow_engine.py` — 工作流状态机（init→preprocessing→analyzing→executing→completed/failed/paused）
  - `workflow_analyzer.py` — 文件扫描 + 仓库类型分类 + LLM 任务列表生成
  - `workflow_executor.py` — DeepAgent 驱动的任务执行 + 索引生成
  - `workflow_preprocess.py` — 预处理（local_path / git_url / archive）
- `models/schemas.py` — Pydantic 请求/响应模型

### 数据库

SQLite 位于 `backend/data/answeragent.db`，4 张表：
- `users` — 用户账户（bcrypt 密码哈希）
- `conversations` — 对话元数据（消息内容存 JSON 文件）
- `model_config` — 运行时配置（key-value）
- `kb_workflow_tasks` — 知识库生成工作流状态

### 知识库与检索流程

1. `kb_router.py` 扫描 `knowledge/` 并用 LLM 判断问题匹配的知识库
2. `file_loader.py` 对每个匹配知识库进行两阶段文件选择
3. 将选定文件内容合并为上下文
4. `agent_builder.py` 根据 `mode` 构建对应 DeepAgent
5. 通过 `agent.astream_events(version="v3")` 消费流式事件，映射为 SSE
6. 深度思考模式（`mode=deep`）额外发出 `agent_think` / `agent_observe` 事件

### Skills 系统

`backend/skills/` 目录下的技能文件（SKILL.md）在 agent 构建时自动加载为虚拟文件，注入到 DeepAgents 的 StateBackend 中。内置 `kb-generator` 技能用于知识库生成工作流。

Docker 部署时，内置 skills 打包为 `skills_builtin/`，启动时由 entrypoint 脚本同步到 `/app/skills/`（跳过已存在的 skill）。

### 前端目录

`frontend/src/`，技术栈 Vue 3 + TypeScript + Vite + Pinia：

- `api/index.ts` — HTTP 请求 + SSE 封装（axios + @microsoft/fetch-event-source）
- `router/index.ts` — Hash 路由 + 认证守卫
- `stores/auth.ts` — 认证状态
- `stores/chat.ts` — 聊天状态（对话列表、流式消息、主题）
- `components/` — ChatWindow、ConversationSidebar、InputBar
- `components/admin/` — ModelConfig、UserManagement、ConversationManagement、KbWorkflow
- `views/` — ChatView、LoginView、RegisterView、AdminView、AdminLoginView
- `types/index.ts` — TypeScript 类型定义

### Docker 部署

- `docker-compose.yml` — backend + frontend 双容器
- `backend/Dockerfile` — python:3.11-slim，ENTRYPOINT 为 docker-entrypoint.sh
- `backend/docker-entrypoint.sh` — 启动时同步内置 skills
- `frontend/Dockerfile` — node:20-alpine 多阶段构建 → nginx:alpine

## 设计约束

- 不使用向量数据库或 embedding RAG，使用"关键词粗筛 + LLM 精读"
- 流式输出使用 SSE（POST），不是 WebSocket
- 对话消息存 JSON 文件，元数据存 SQLite
- 所有文件操作必须 `resolve()` + `relative_to()` 校验防路径穿越
- 单文件上限 20KB，单知识库上限 60KB