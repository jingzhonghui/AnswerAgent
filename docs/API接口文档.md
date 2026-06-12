# AnswerAgent API 接口文档

> 版本 0.1.0 | 基础地址 `http://localhost:8765`

---

## 目录

- [1. 概述](#1-概述)
- [2. 认证](#2-认证)
- [3. 对话管理](#3-对话管理)
- [4. 聊天（SSE 流式）](#4-聊天sse-流式)
- [5. 知识库](#5-知识库)
- [6. 管理后台](#6-管理后台)
- [7. 通用](#7-通用)
- [8. 数据模型](#8-数据模型)

---

## 1. 概述

### 认证方式

除注册/登录外，所有接口需在请求头携带 JWT：

```
Authorization: Bearer <access_token>
```

### 响应格式

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 删除成功（无响应体） |
| 400 | 请求参数错误 |
| 401 | 未认证或认证过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如用户名已存在） |

---

## 2. 认证

### 2.1 用户注册

```
POST /api/auth/register
```

**请求体：**

```json
{
  "username": "string (2-50字符)",
  "password": "string (6-100字符)"
}
```

**响应（201）：**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "string",
    "is_admin": false,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

### 2.2 用户登录

```
POST /api/auth/login
```

**请求体：**

```json
{
  "username": "string",
  "password": "string"
}
```

**响应（200）：**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "string",
    "is_admin": true,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

### 2.3 获取当前用户

```
GET /api/auth/me
```

**响应（200）：**

```json
{
  "id": "uuid",
  "username": "string",
  "is_admin": false,
  "created_at": "2024-01-01T00:00:00"
}
```

### 2.4 修改密码

```
POST /api/auth/change-password
```

**请求体：**

```json
{
  "old_password": "string",
  "new_password": "string (6-100字符)"
}
```

**响应（200）：**

```json
{
  "message": "密码修改成功"
}
```

---

## 3. 对话管理

### 3.1 获取对话列表

```
GET /api/conversations
```

返回当前用户的所有对话，按 `updated_at` 倒序。

**响应（200）：**

```json
[
  {
    "id": "uuid",
    "title": "对话标题",
    "kb_names": ["知识库A"],
    "updated_at": "2024-01-01T00:00:00",
    "message_count": 12
  }
]
```

### 3.2 创建对话

```
POST /api/conversations
```

**请求体：**

```json
{
  "title": "新对话"
}
```

**响应（201）：**

```json
{
  "id": "uuid",
  "title": "新对话"
}
```

### 3.3 获取对话详情

```
GET /api/conversations/{conversation_id}
```

**响应（200）：**

```json
{
  "id": "uuid",
  "title": "对话标题",
  "kb_names": ["知识库A"],
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "你好"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "你好！有什么可以帮助你的？",
      "kb_names": ["知识库A"],
      "files_used": [
        {
          "kb_name": "知识库A",
          "file_path": "doc/readme.md",
          "file_name": "readme.md"
        }
      ],
      "thinking_steps": []
    }
  ],
  "user_id": "uuid"
}
```

### 3.4 重命名对话

```
PATCH /api/conversations/{conversation_id}/title
```

**请求体：**

```json
{
  "title": "新标题 (1-200字符)"
}
```

**响应（200）：**

```json
{
  "id": "uuid",
  "title": "新标题"
}
```

### 3.5 删除对话

```
DELETE /api/conversations/{conversation_id}
```

**响应（204）：** 无响应体

### 3.6 导出对话

```
GET /api/conversations/{conversation_id}/export
```

**响应（200）：** Markdown 文件下载

---

## 4. 聊天（SSE 流式）

### 4.1 发送消息（SSE 流式问答）

```
POST /api/chat/stream
```

**请求体：**

```json
{
  "conversation_id": "uuid",
  "message": "string",
  "mode": "default"
}
```

`mode` 可选值：
- `"default"` — 标准 LCEL 问答链
- `"deep"` — ReAct Agent 深度思考模式
- `"agent"` — 预留，当前返回错误

**响应：** `text/event-stream`（SSE）

### SSE 事件类型

#### `kb_matched` — 知识库匹配完成

```
event: kb_matched
data: {"kb_names": ["知识库A", "知识库B"]}
```

#### `files_selected` — 文件选取完成（每个知识库一次）

```
event: files_selected
data: {"kb": "知识库A", "files": ["doc/a.md", "doc/b.md"]}
```

#### `token` — 流式内容片段

```
event: token
data: {"content": "你好"}
```

#### `agent_think` — 深度思考步骤（仅 deep 模式）

```
event: agent_think
data: {
  "step": "action",
  "thought": "用户想知道...",
  "tool": "search_knowledge",
  "tool_input": "{...}"
}
```

#### `agent_observe` — 工具执行结果（仅 deep 模式）

```
event: agent_observe
data: {
  "step": "observation",
  "result": "工具返回的内容..."
}
```

#### `done` — 回答完成

```
event: done
data: {"message_id": "uuid", "title": "自动生成的标题"}
```

#### `error` — 错误

```
event: error
data: {"message": "错误描述"}
```

### 完整 SSE 流示例（default 模式）

```
event: kb_matched
data: {"kb_names":["技术文档"]}

event: files_selected
data: {"kb":"技术文档","files":["api.md","guide.md"]}

event: token
data: {"content":"根据"}

event: token
data: {"content":"知识库"}

...

event: done
data: {"message_id":"abc-123"}
```

### 对话自动创建

如果 `conversation_id` 不存在或不属于当前用户，服务端会自动创建新对话。

### 4.2 外部流式聊天（免登录）

```
POST /api/chat/external/stream
```

> 无需认证，不持久化对话，供外部系统直接接入。

**请求体：**

```json
{
  "message": "string (必填)",
  "mode": "default",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 用户消息内容 |
| `mode` | string | ❌ | `"default"` 或 `"deep"`，默认 `"default"` |
| `history` | array | ❌ | 可选历史消息列表，每项含 `role`（`"user"`/`"assistant"`）和 `content` |

**响应：** `text/event-stream`（SSE），事件类型与 4.1 完全一致，但 `done` 事件返回空对象 `{}`（无 `message_id` 和 `title`）。

> 详细对接文档见 [外部接口对接文档](./外部接口对接文档.md)。

---

## 5. 知识库

### 5.1 获取知识库列表

```
GET /api/knowledge-bases
```

**响应（200）：**

```json
["技术文档", "产品手册", "API参考"]
```

---

## 6. 管理后台

> 所有管理后台接口需要管理员权限（JWT 中 `is_admin=true`）。

### 6.1 模型配置

#### 获取全部配置

```
GET /api/admin/model-config
```

**响应（200）：**

```json
{
  "configs": [
    {
      "key": "llm_provider",
      "value": "openai",
      "description": "默认模型提供商（openai / anthropic）",
      "sensitive": false,
      "restart_required": false
    },
    {
      "key": "api_key",
      "value": "sk-xxx",
      "description": "默认模型 API Key",
      "sensitive": false,
      "restart_required": false
    },
    {
      "key": "history_window",
      "value": "10",
      "description": "对话历史保留轮数（每轮 = 1问1答），默认 10",
      "sensitive": false,
      "restart_required": false
    },
    {
      "key": "knowledge_path",
      "value": "./knowledge",
      "description": "知识库根目录路径（⚠️ 需重启生效），默认 ./knowledge",
      "sensitive": false,
      "restart_required": true
    }
  ]
}
```

> 敏感配置（`jwt_secret_key`、`admin_default_password`）不在返回结果中。

#### 批量更新配置

```
PUT /api/admin/model-config
```

**请求体：**

```json
{
  "configs": [
    { "key": "model", "value": "gpt-4o" },
    { "key": "temperature", "value": "0.8" }
  ]
}
```

**响应（200）：**

```json
{
  "message": "配置已更新，即时生效",
  "updated": ["model", "temperature"]
}
```

> 禁止通过 API 修改敏感配置（`jwt_secret_key`、`admin_default_password`），会返回 403。

### 6.2 用户管理

#### 获取用户列表

```
GET /api/admin/users
```

**响应（200）：**

```json
[
  {
    "id": "uuid",
    "username": "admin",
    "is_admin": true,
    "created_at": "2024-01-01T00:00:00",
    "conversation_count": 5
  }
]
```

#### 创建用户

```
POST /api/admin/users
```

**请求体：**

```json
{
  "username": "newuser (2-50字符)",
  "password": "password123 (6-100字符)",
  "is_admin": false
}
```

**响应（201）：** 同用户列表项的格式

#### 更新用户

```
PUT /api/admin/users/{user_id}
```

**请求体：**

```json
{
  "is_admin": true
}
```

> 不能取消自己的管理员权限。

**响应（200）：** 同用户列表项的格式

#### 删除用户

```
DELETE /api/admin/users/{user_id}
```

> 会级联删除该用户的所有对话。不能删除自己。

**响应（204）：** 无响应体

### 6.3 会话管理

#### 获取所有对话

```
GET /api/admin/conversations?user_id=&search=
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | 否 | 按用户 ID 筛选 |
| `search` | string | 否 | 按标题模糊搜索 |

**响应（200）：**

```json
[
  {
    "id": "uuid",
    "title": "对话标题",
    "user_id": "uuid",
    "username": "user1",
    "message_count": 12,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00"
  }
]
```

> 最多返回 500 条。

#### 查看任意对话

```
GET /api/admin/conversations/{conversation_id}
```

管理员不受对话所有权限制。

**响应（200）：** 同 [3.3 对话详情](#33-获取对话详情)

#### 删除任意对话

```
DELETE /api/admin/conversations/{conversation_id}
```

管理员不受对话所有权限制。

**响应（204）：** 无响应体

---

## 7. 通用

### 7.1 健康检查

```
GET /api/health
```

**响应（200）：**

```json
{
  "status": "ok",
  "message": "AnswerAgent is running"
}
```

---

## 8. 数据模型

### Message

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string? | 消息 UUID |
| `role` | string | `"user"` 或 `"assistant"` |
| `content` | string | 消息内容 |
| `kb_names` | string[]? | 参考的知识库名称 |
| `files_used` | FileSelection[]? | 参考的文件列表 |
| `thinking_steps` | ThinkingStep[]? | 深度思考步骤（仅 assistant + deep 模式） |
| `created_at` | datetime? | 创建时间 |

### FileSelection

| 字段 | 类型 | 说明 |
|------|------|------|
| `kb_name` | string | 知识库名称 |
| `file_path` | string | 知识库内相对路径 |
| `file_name` | string | 文件名 |

### ThinkingStep

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"action"` 或 `"observation"` |
| `thought` | string? | Agent 推理文本（action） |
| `tool` | string? | 工具名（action） |
| `toolInput` | string? | 工具输入（action） |
| `result` | string? | 工具返回结果（observation） |

### ConversationSummary

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 对话 UUID |
| `title` | string | 对话标题 |
| `kb_names` | string[] | 关联知识库 |
| `updated_at` | datetime | 最后更新时间 |
| `message_count` | int? | 消息数量 |

### ConversationDetail

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 对话 UUID |
| `title` | string | 对话标题 |
| `kb_names` | string[] | 关联知识库 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 最后更新时间 |
| `messages` | Message[] | 全部消息 |
| `user_id` | string? | 所属用户 ID |

### UserResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 UUID |
| `username` | string | 用户名 |
| `is_admin` | bool | 是否管理员 |
| `created_at` | datetime | 注册时间 |

### ModelConfigItem

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | string | 配置键 |
| `value` | string | 配置值 |
| `description` | string | 配置说明 |
| `sensitive` | bool? | 是否为敏感配置 |
| `restart_required` | bool? | 是否需要重启生效 |

### 配置键完整列表

| 键名 | 分类 | 热更新 | 说明 |
|------|------|--------|------|
| `llm_provider` | 默认模型 | ✅ | 提供商：`openai` / `anthropic` |
| `api_key` | 默认模型 | ✅ | API Key |
| `base_url` | 默认模型 | ✅ | API Base URL |
| `model` | 默认模型 | ✅ | 模型名称 |
| `temperature` | 默认模型 | ✅ | 温度（0.0~2.0） |
| `deep_model_enabled` | 深度思考 | ✅ | 是否启用（`true`/`false`） |
| `deep_llm_provider` | 深度思考 | ✅ | 提供商（空则复用默认） |
| `deep_api_key` | 深度思考 | ✅ | API Key（空则复用默认） |
| `deep_base_url` | 深度思考 | ✅ | Base URL（空则复用默认） |
| `deep_model` | 深度思考 | ✅ | 模型名称 |
| `deep_temperature` | 深度思考 | ✅ | 温度（0.0~2.0） |
| `history_window` | 系统 | ✅ | 对话历史保留轮数 |
| `knowledge_path` | 系统 | ❌ | 知识库根目录 |
| `data_path` | 系统 | ❌ | 对话数据存储路径 |
| `jwt_algorithm` | 系统 | ❌ | JWT 签名算法 |
| `jwt_expire_minutes` | 系统 | ❌ | JWT 过期时间（分钟） |
| `jwt_secret_key` | 🔒 敏感 | ❌ | JWT 签名密钥 |
| `admin_default_password` | 🔒 敏感 | 仅首次 | 默认管理员初始密码 |
