# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 当前仓库状态

当前仓库主要包含项目设计文档，尚未提交设计文档中规划的 `backend/`、`frontend/`、`README.md`、`requirements.txt` 或 `package.json`。因此，下面的开发命令来自 `docs/设计方案.md` 中的规划；在实际执行前应先确认对应目录和配置文件已经落地。

## 常用命令

### 后端（规划）

设计文档描述后端位于 `backend/`，使用 Python + FastAPI，并在 `app/main.py` 末尾内嵌 `uvicorn.run()`：

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
python main.py
```

后端服务规划启动于 `http://localhost:8000`。

### 前端（规划）

设计文档描述前端位于 `frontend/`，使用 Vue 3 + TypeScript + Vite：

```bash
cd frontend
npm install
npm run dev
```

前端开发服务规划启动于 `http://localhost:5173`。

### 测试、lint、构建

当前仓库没有实际的测试、lint 或构建配置文件。不要在未确认配置存在前假设存在 `pytest`、`npm test`、`npm run lint` 或 `npm run build`。

## 高层架构

AnswerAgent 被设计为一个基于本地文件目录的问答智能体：后端从本地知识库中检索相关文件内容，再通过 LangChain 调用 OpenAI 或 Anthropic 模型生成回答；前端通过 SSE 展示流式输出。

### 后端设计

规划中的后端目录为 `backend/app/`：

- `api/`：FastAPI 路由层，包含流式问答、对话 CRUD、知识库列表接口。
- `core/config.py`：通过 Pydantic Settings 读取 `.env` 配置，包括 LLM provider、模型、知识库路径、数据路径和历史窗口。
- `core/llm_factory.py`：统一创建 LangChain LLM，支持 OpenAI 与 Anthropic。
- `core/kb_router.py`：扫描知识库并判断用户问题匹配哪些知识库，支持多知识库匹配。
- `core/file_loader.py`：执行文件选取流程，先做本地关键词粗筛，再让 LLM 从候选摘要中选择最相关文件。
- `core/chain_builder.py`：构建 LCEL 问答链，注入知识库上下文、对话历史和当前问题。
- `core/chat_manager.py`：以 JSON 文件方式持久化对话。
- `models/schemas.py`：定义 Pydantic 请求和响应模型。

后端规划依赖包括 FastAPI、uvicorn、python-dotenv、pydantic-settings、LangChain、langchain-openai、langchain-anthropic、sse-starlette 和 jieba。

### 知识库与检索流程

知识库规划位于 `backend/knowledge/{知识库名称}/`。每个知识库可以包含可选的 `索引.md`、Markdown 文档和可选的 `src/` 源码目录。

问答流程为：

1. `kb_router.py` 扫描 `knowledge/` 并用 LLM 判断问题匹配的知识库。
2. `file_loader.py` 对每个匹配知识库进行两阶段文件选择：本地关键词粗筛候选文件，再由 LLM 基于候选摘要选择最相关文件。
3. 将多个知识库中选定文件内容合并为上下文。
4. `chain_builder.py` 通过 LangChain LCEL 链注入上下文、最近 `HISTORY_WINDOW` 轮对话历史和当前问题。
5. 后端通过 SSE 将匹配知识库、选中文件、token、完成或错误事件推给前端。

如果没有匹配知识库，设计中会走通用问答链，只注入对话历史和当前问题。

### SSE 协议

规划中的流式接口为 `POST /api/chat/stream`，事件包括：

- `kb_matched`：返回匹配到的知识库名称列表。
- `files_selected`：返回某个知识库被选中的参考文件。
- `token`：返回流式生成内容片段。
- `done`：返回回答完成事件和消息 ID。
- `error`：返回错误信息。

### 对话持久化

对话规划以独立 JSON 文件保存到 `backend/data/conversations/{id}.json`。每个文件包含对话 ID、标题、关联知识库、创建/更新时间和消息列表。消息中 assistant 记录可包含 `kb_names` 和 `files_used`。

### 前端设计

规划中的前端目录为 `frontend/src/`，技术栈是 Vue 3、TypeScript、Vite、Pinia、axios、markdown-it、highlight.js 和原生 EventSource。

核心结构：

- `api/index.ts`：封装 HTTP 请求和 SSE 接收。
- `stores/chat.ts`：Pinia 聊天状态，管理对话列表、当前消息、流式状态、知识库匹配结果、选中文件和主题。
- `components/`：侧边栏、聊天窗口、消息气泡、输入栏和知识库标签。
- `types/index.ts`：Conversation、Message、FileSelection、SSE event 等类型定义。
- `styles/`：CSS 变量和全局样式，通过 `data-theme="dark"` 切换亮色/暗色主题，偏好存入 `localStorage`。

前端交互规划为：发送问题后显示匹配状态；收到 `kb_matched` 后显示知识库标签；收到 `files_selected` 后显示参考文件；收到 `token` 后追加内容；收到 `done` 后结束流式状态；流式进行中发送按钮变为停止按钮并可 abort SSE 连接。

## 设计约束

- 项目设计明确选择“关键词粗筛 + LLM 精读决策”，不使用向量数据库或 embedding RAG。
- 流式输出使用 SSE，而不是 WebSocket。
- 对话数据使用独立 JSON 文件持久化，而不是数据库。
