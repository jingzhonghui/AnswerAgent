# AnswerAgent 项目概述

AnswerAgent 是一个基于本地文件目录的问答智能体。后端使用 Python + FastAPI，
前端使用 Vue 3 + TypeScript。通过 LangChain 统一封装 OpenAI / Anthropic 模型调用。

## 核心特性

- 基于本地文件目录的知识库管理，无需向量数据库
- 多知识库自动匹配，结果可合并
- SSE 流式输出，前端实时展示 token
- 多对话管理：新建、重命名、删除、按时间分组
- 亮 / 暗双主题，主题偏好持久化到 localStorage
- 对话以独立 JSON 文件持久化，零数据库依赖

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + uvicorn |
| LLM 框架 | LangChain（LCEL）|
| LLM 提供商 | OpenAI、Anthropic |
| 流式协议 | SSE（POST + sse-starlette）|
| 中文分词 | jieba |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| Markdown 渲染 | markdown-it + highlight.js |

## 不使用的方案

- 不使用向量数据库（Chroma / Faiss）和 Embedding 模型
- 不使用 WebSocket（采用单向 SSE）
- 不使用数据库（对话以 JSON 文件持久化）
