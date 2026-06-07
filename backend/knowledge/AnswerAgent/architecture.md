# 后端架构与问答流程

## 模块划分

```
backend/app/
├── api/
│   ├── chat.py             # SSE 流式问答接口（M3）
│   ├── conversations.py    # 对话 CRUD 接口
│   └── knowledge_bases.py  # 知识库列表接口
├── core/
│   ├── config.py           # Pydantic Settings 读取 .env
│   ├── llm_factory.py      # 统一创建 LangChain Chat Model
│   ├── kb_router.py        # 知识库扫描与 LLM 路由
│   ├── file_loader.py      # 两阶段文件选取
│   ├── chain_builder.py    # LCEL 问答链（M3）
│   └── chat_manager.py     # 对话 JSON 持久化
├── models/
│   └── schemas.py          # Pydantic 请求/响应模型
└── main.py                 # FastAPI 入口，内嵌 uvicorn.run()
```

## 问答核心流程

1. **知识库路由**：`kb_router.py` 扫描 `KNOWLEDGE_PATH` 一级目录，
   将候选知识库（含 `索引.md` 预览）交给 LLM 多选。
2. **文件选取**（每个匹配知识库并行执行）：
   - 阶段 1 关键词粗筛：jieba + 英文 token 在文件名、标题、`索引.md` 中评分，取 Top 10。
   - 阶段 2 LLM 精读：候选目录交 LLM 选 ≤ 5 文件。
3. **上下文合并**：所有知识库选定文件内容合并，单文件 20KB、单知识库 60KB 上限。
4. **LCEL 问答链**：注入合并上下文、最近 N 轮历史、当前问题，LLM 流式生成。
5. **SSE 推送**：依次发出 `kb_matched → files_selected* → token* → done`。

## 路径安全

所有知识库文件读取必须 `resolve()` 后用 `relative_to(kb_root)` 校验，
确保实际路径仍在知识库根目录内，禁止路径穿越。
