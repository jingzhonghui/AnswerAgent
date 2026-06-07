# 对话 JSON 持久化结构

对话不使用数据库，每个对话保存为独立 JSON 文件，
位于 `backend/data/conversations/{uuid}.json`。

## JSON 数据结构

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "如何使用 SSE 协议",
  "kb_names": ["AnswerAgent"],
  "created_at": "2026-06-07T10:00:00",
  "updated_at": "2026-06-07T10:05:00",
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "如何使用 SSE 协议？",
      "created_at": "2026-06-07T10:00:00"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "...",
      "kb_names": ["AnswerAgent"],
      "files_used": [
        {"kb_name": "AnswerAgent", "file_path": "sse-protocol.md", "file_name": "sse-protocol.md"}
      ],
      "created_at": "2026-06-07T10:00:05"
    }
  ]
}
```

## 安全约束

- 文件名必须为合法 UUID（`chat_manager._validate_conversation_id` 校验）。
- 读写前路径 resolve 后必须仍在 `DATA_PATH` 内，防止穿越。
- 写入采用原子操作：先写临时文件再 `os.replace`，避免半写损坏。

## 历史窗口

`chat_manager.get_recent_history(window=N)` 返回最近 N 轮消息（每轮 = 1 问 1 答），
默认 N 来自 `.env` 的 `HISTORY_WINDOW=10`。
