# AnswerAgent 开发指南

## 项目状态

代码已实现（**不是**设计阶段）。`CLAUDE.md` 是过时的设计文档，**不可信**——实际实现有认证、SQLite、前端路由等多出规划。

## 启动命令

```bash
# 后端（backend/ 目录下）
pip install -r requirements.txt
cp .env.example .env   # 填入 API key
python -m app.main     # 监听 0.0.0.0:8765

# 前端（frontend/ 目录下）
npm install
npm run dev            # 监听 localhost:5173，/api 代理到 :8765
```

## 测试

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## 构建

```bash
cd frontend
npm run build    # vue-tsc --noEmit + vite build
```

## 架构要点

- **后端端口 8765**（不是 8000，CLAUDE.md 错误）
- **JWT 认证**：所有接口（除了 `/api/auth/register`、`/api/auth/login`）都需要 `Authorization: Bearer <token>`；SSE 接口手动认证，不能用 Depends
- **双存储**：对话元数据（标题、用户归属）存 SQLite，消息内容存 `data/conversations/{id}.json`
- **SQLite 路径**: `backend/data/answeragent.db`（`__init__` 中自动创建）
- **检索不依赖向量数据库**：关键词粗筛（jieba 分词）→ LLM 精读选择文件
- **前端 SSE 使用 `@microsoft/fetch-event-source`**（不是原生 EventSource，因为需要 POST）
- **前端类型检查严格**：`noUnusedLocals`、`noUnusedParameters` 开启，`vue-tsc` 必须通过

## 知识库结构

```
backend/knowledge/{知识库名称}/
├── 索引.md          # 可选，供 kb_router/file_loader 做路由提示
├── overview.md
└── src/
```

知识库名不能以 `.` 开头。文件类型仅白名单后缀（`.md`、`.py`、`.ts`、`.vue`、`.json` 等）。

## 约束

- 流式用 SSE + POST，不用 WebSocket
- 文件读取必须 `resolve()` + `relative_to()` 校验防路径穿越
- 单文件上限 20KB，单知识库上限 60KB
- 不要新增大依赖（没有 requirements.txt 中不存在的库）
- 前端路径别名 `@/` → `src/`
