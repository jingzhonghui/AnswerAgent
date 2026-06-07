"""SSE 事件序列化示例

将 Pydantic 事件模型 dump 成 SSE 帧字符串，
用于 sse-starlette 的 EventSourceResponse。

注意:
- 每帧 data 必须是单行字符串，因此 JSON 不带缩进。
- 帧之间用 \\n\\n 分隔。
"""
import json
from typing import Any


def to_sse_frame(event_type: str, payload: dict[str, Any]) -> str:
    """将事件序列化为 SSE 帧字符串

    Args:
        event_type: 事件类型，如 "kb_matched" / "token" / "done"
        payload: 事件数据，会被 json.dumps 编码

    Returns:
        str: 形如 "event: kb_matched\\ndata: {...}\\n\\n"
    """
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_type}\ndata: {body}\n\n"


# 使用示例
if __name__ == "__main__":
    print(to_sse_frame("kb_matched", {"kb_names": ["AnswerAgent"]}))
    print(to_sse_frame("token", {"content": "你好"}))
    print(to_sse_frame("done", {"message_id": "abc-123"}))
