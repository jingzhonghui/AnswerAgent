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
  sensitive?: boolean
  restart_required?: boolean
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

// ============================================================
// 知识库生成工作流类型
// ============================================================

export type InputType = 'local_path' | 'git_url' | 'archive'

export type WorkflowStatus = 'pending' | 'preprocessing' | 'analyzing' | 'executing' | 'completed' | 'failed' | 'paused'

export interface AnalysisTask {
  id: string
  description: string
  target_file: string
  dependencies: string[]
}

export interface WorkflowTask {
  id: string
  status: WorkflowStatus
  input_type: InputType
  input_value: string
  knowledge_name: string | null
  repo_type: string | null
  stage: string
  stage_progress: Record<string, any>
  task_list: AnalysisTask[]
  completed_tasks: string[]
  result_path: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface StartWorkflowRequest {
  input_type: InputType
  input_value: string
}

export interface StartWorkflowResponse {
  task_id: string
  status: string
}

export interface WorkflowLogEntry {
  timestamp: string
  message: string
}

// ============================================================
// 知识库管理类型
// ============================================================

/** 知识库摘要信息 */
export interface KbSummary {
  name: string
  file_count: number
  last_modified: string | null
  total_size: number
}

/** 知识库内文件/目录信息 */
export interface KbFileInfo {
  name: string
  rel_path: string
  size: number
  modified: string
  extension: string
  is_dir: boolean
}

/** 知识库文件列表（文件浏览器模式） */
export interface KbFileList {
  kb_name: string
  current_path: string
  items: KbFileInfo[]
}

/** 创建知识库请求 */
export interface CreateKbRequest {
  name: string
}