// TypeScript 类型定义

export interface ConversationSummary {
  id: string
  title: string
  kb_names: string[]
  updated_at: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  kb_names?: string[]
  files_used?: string[]
  timestamp: string
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
  created_at: string
}

export interface RenameConversationRequest {
  title: string
}
