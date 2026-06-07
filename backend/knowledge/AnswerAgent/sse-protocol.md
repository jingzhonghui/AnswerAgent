# SSE 流式事件协议

流式问答接口 `POST /api/chat/stream` 返回以下 SSE 事件序列。
每个 `data:` 字段都是一个 JSON 字符串。

## 事件清单

| 事件名 | 数据示例 | 触发时机 |
|---|---|---|
| `kb_matched` | `{"kb_names": ["AnswerAgent"]}` | 路由完成后立即发出，无匹配时数组为空 |
| `files_selected` | `{"kb": "AnswerAgent", "files": ["overview.md"]}` | 每个知识库选完文件后发一次 |
| `token` | `{"content": "根据"}` | LLM 每产生一个增量 token |
| `done` | `{"message_id": "uuid"}` | 流式完成，含 assistant 消息 ID |
| `error` | `{"message": "错误描述"}` | 任意阶段异常 |

## 为什么用 POST + SSE 而不是原生 EventSource

原生浏览器 `EventSource` 只支持 GET，无法发送 JSON body。
本项目发送消息会创建/更新对话，存在副作用，语义上应为 POST。
因此前端使用 `@microsoft/fetch-event-source` 来消费 POST SSE 响应。

## 为什么是 SSE 而非 WebSocket

SSE 是单向推送（服务器 → 客户端），原生支持，无需额外鉴权握手协议。
WebSocket 适合双向实时通信（如多人协作），本项目用不上。

## 客户端断开处理

客户端调用 `AbortController.abort()` 后，FastAPI 端检测到连接断开
应立即停止 LLM 生成并清理资源，避免无谓 token 消耗。
