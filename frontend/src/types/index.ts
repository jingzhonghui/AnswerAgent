// TypeScript 类型定义

export interface FileRef {
  kb_name: string
  file_path: string
  file_name: string
}

export interface ConversationSummary {
  id: string
  title: string
  kb_names: string[]
  updated_at: string
  message_count?: number
}

export interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
  kb_names?: string[]
  files_used?: FileRef[]
  thinking_steps?: ThinkingStep[]
  timestamp?: string
  created_at?: string
}

export interface Conversation {
  id: string
  title: string
  kb_names: string[]
  created_at: string
  updated_at: string
  messages: Message[]
}

export interface FileSelection {
  kb: string
  files: string[]
}

export type SseEvent =
  | { type: 'kb_matched'; kb_names: string[] }
  | { type: 'files_selected'; kb: string; files: string[] }
  | { type: 'token'; content: string }
  | { type: 'done'; message_id: string }
  | { type: 'error'; message: string }

export interface CreateConversationResponse {
  id: string
  title: string
}

export interface RenameConversationRequest {
  title: string
}

/** 深度思考：单个推理步骤 */
export interface ThinkingStep {
  /** 'action' | 'observation' */
  type: 'action' | 'observation'
  /** 思考内容（仅 action） */
  thought?: string
  /** 工具名（仅 action） */
  tool?: string
  /** 工具输入（仅 action） */
  toolInput?: string
  /** 工具返回结果（仅 observation） */
  result?: string
}

// ============================================================
// Admin 类型
// ============================================================

/** 模型配置项 */
export interface ModelConfigItem {
  key: string
  value: string
  description: string
}

/** 管理员视角的用户信息 */
export interface AdminUserInfo {
  id: string
  username: string
  is_admin: boolean
  created_at: string
  conversation_count: number
}

/** 管理员视角的对话摘要 */
export interface AdminConversationSummary {
  id: string
  title: string
  user_id: string | null
  username: string | null
  message_count: number
  created_at: string
  updated_at: string
}