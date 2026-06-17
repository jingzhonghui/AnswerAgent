import axios, { type AxiosInstance } from 'axios'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import type {
  ConversationSummary,
  Conversation,
  CreateConversationResponse,
  RenameConversationRequest,
  ModelConfigItem,
  AdminUserInfo,
  AdminConversationSummary,
  WorkflowTask,
  StartWorkflowRequest,
  StartWorkflowResponse,
  WorkflowLogEntry,
} from '@/types'

// axios 实例配置
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - 自动附加 Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 - 错误处理 + 401 自动跳转登录
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      // 根据当前所在页面跳转到对应的登录页
      const hash = window.location.hash
      if (hash.includes('/admin')) {
        window.location.href = '/#/admin/login'
      } else {
        window.location.href = '/#/login'
      }
    }
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// 获取对话列表 -> GET /api/conversations
export async function getConversations(): Promise<ConversationSummary[]> {
  const response = await api.get<ConversationSummary[]>('/conversations')
  return response.data
}

// 新建对话 -> POST /api/conversations
export async function createConversation(title?: string): Promise<CreateConversationResponse> {
  const response = await api.post<CreateConversationResponse>('/conversations', {
    title: title || '新对话',
  })
  return response.data
}

// 获取对话详情 -> GET /api/conversations/{id}
export async function getConversation(id: string): Promise<Conversation> {
  const response = await api.get<Conversation>(`/conversations/${id}`)
  return response.data
}

// 删除对话 -> DELETE /api/conversations/{id}
export async function deleteConversation(id: string): Promise<void> {
  await api.delete(`/conversations/${id}`)
}

// 重命名对话 -> PATCH /api/conversations/{id}/title
export async function renameConversation(id: string, title: string): Promise<void> {
  const data: RenameConversationRequest = { title }
  await api.patch(`/conversations/${id}/title`, data)
}

// 导出对话为 Markdown -> GET /api/conversations/{id}/export
export async function exportConversation(id: string, filename: string): Promise<void> {
  const response = await api.get(`/conversations/${id}/export`, {
    responseType: 'blob',
  })
  // 触发浏览器下载
  const url = URL.createObjectURL(new Blob([response.data], { type: 'text/markdown; charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// SSE 流式问答 -> POST /api/chat/stream
export interface StreamChatHandlers {
  onKbMatched: (kbNames: string[]) => void
  onFilesSelected: (kb: string, files: string[]) => void
  onToken: (content: string) => void
  onDone: (messageId: string, title?: string) => void
  onError: (message: string) => void
  /** 上下文预算裁剪通知 */
  onContextTrimmed?: (data: { trimmed_history_rounds: number; trimmed_context_chars: number; char_used: number; char_budget: number }) => void
  /** 深度思考：Agent 推理/行动决策 */
  onAgentThink?: (step: string, thought: string, tool: string, toolInput: string) => void
  /** 深度思考：工具执行结果 */
  onAgentObserve?: (step: string, result: string) => void
}

export async function streamChat(
  request: {
    conversation_id: string
    message: string
    mode: string
  },
  handlers: StreamChatHandlers,
  signal: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  await fetchEventSource('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token || ''}`,
    },
    body: JSON.stringify(request),
    signal,
    onmessage(event) {
      if (!event.data) return
      try {
        const data = JSON.parse(event.data)
        switch (event.event) {
          case 'kb_matched':
            handlers.onKbMatched(data.kb_names || [])
            break
          case 'files_selected':
            handlers.onFilesSelected(data.kb || '', data.files || [])
            break
          case 'token':
            handlers.onToken(data.content || '')
            break
          case 'done':
            handlers.onDone(data.message_id || '', data.title ?? undefined)
            break
          case 'context_trimmed':
            handlers.onContextTrimmed?.(data)
            break
          case 'agent_think':
            handlers.onAgentThink?.(
              data.step || '',
              data.thought || '',
              data.tool || '',
              data.tool_input || '',
            )
            break
          case 'agent_observe':
            handlers.onAgentObserve?.(data.step || '', data.result || '')
            break
          case 'error':
            handlers.onError(data.message || '未知错误')
            break
        }
      } catch {
        // 忽略解析失败的事件
      }
    },
    onerror(err) {
      // 用户主动 abort 不报错
      if (signal.aborted) {
        throw err
      }
      handlers.onError('连接失败，请重试')
      throw err // 不重试
    },
  })
}

// ============================================================
// Public API（无需认证）
// ============================================================

export interface PublicConfig {
  deep_model_enabled: boolean
}

export async function getPublicConfig(): Promise<PublicConfig> {
  const response = await api.get<PublicConfig>('/public/config')
  return response.data
}

// ============================================================
// Auth API
// ============================================================

export interface AuthUser {
  id: string
  username: string
  is_admin?: boolean
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

export async function apiLogin(username: string, password: string): Promise<AuthTokenResponse> {
  const response = await api.post<AuthTokenResponse>('/auth/login', { username, password })
  return response.data
}

export async function apiRegister(username: string, password: string): Promise<AuthTokenResponse> {
  const response = await api.post<AuthTokenResponse>('/auth/register', { username, password })
  return response.data
}

export async function apiGetMe(): Promise<AuthUser> {
  const response = await api.get<AuthUser>('/auth/me')
  return response.data
}

// 修改密码
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export async function apiChangePassword(data: ChangePasswordRequest): Promise<{ message: string }> {
  const response = await api.post<{ message: string }>('/auth/change-password', data)
  return response.data
}

// ============================================================
// Admin API
// ============================================================

// 获取模型配置
export async function getModelConfig(): Promise<{ configs: ModelConfigItem[] }> {
  const response = await api.get<{ configs: ModelConfigItem[] }>('/admin/model-config')
  return response.data
}

// 更新模型配置
export async function updateModelConfig(configs: { key: string; value: string }[]): Promise<{ message: string }> {
  const response = await api.put<{ message: string }>('/admin/model-config', { configs })
  return response.data
}

// 获取用户列表
export async function getAdminUsers(): Promise<AdminUserInfo[]> {
  const response = await api.get<AdminUserInfo[]>('/admin/users')
  return response.data
}

// 管理员创建用户
export async function createAdminUser(data: { username: string; password: string; is_admin: boolean }): Promise<AdminUserInfo> {
  const response = await api.post<AdminUserInfo>('/admin/users', data)
  return response.data
}

// 更新用户（设置/取消管理员）
export async function updateAdminUser(userId: string, data: { is_admin: boolean }): Promise<AdminUserInfo> {
  const response = await api.put<AdminUserInfo>(`/admin/users/${userId}`, data)
  return response.data
}

// 删除用户
export async function deleteAdminUser(userId: string): Promise<void> {
  await api.delete(`/admin/users/${userId}`)
}

// 管理员重置用户密码
export async function resetUserPassword(userId: string, newPassword: string): Promise<{ message: string }> {
  const response = await api.post<{ message: string }>(`/admin/users/${userId}/reset-password`, {
    new_password: newPassword,
  })
  return response.data
}

// 获取所有对话（管理员视角）
export async function getAdminConversations(params?: { user_id?: string; search?: string }): Promise<AdminConversationSummary[]> {
  const response = await api.get<AdminConversationSummary[]>('/admin/conversations', { params })
  return response.data
}

// 查看任意对话详情
export async function getAdminConversation(id: string): Promise<Conversation> {
  const response = await api.get<Conversation>(`/admin/conversations/${id}`)
  return response.data
}

// 删除任意对话
export async function deleteAdminConversation(id: string): Promise<void> {
  await api.delete(`/admin/conversations/${id}`)
}

// ============================================================
// 知识库生成工作流 API
// ============================================================

/** 启动工作流（路径/Git 方式） */
export async function startWorkflow(data: StartWorkflowRequest): Promise<StartWorkflowResponse> {
  const response = await api.post<StartWorkflowResponse>('/admin/workflow/start', data)
  return response.data
}

/** 上传压缩包启动工作流 */
export async function startWorkflowUpload(file: File): Promise<StartWorkflowResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post<StartWorkflowResponse>('/admin/workflow/start/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return response.data
}

/** 获取工作流状态 */
export async function getWorkflowStatus(id: string): Promise<WorkflowTask> {
  const response = await api.get<WorkflowTask>(`/admin/workflow/status/${id}`)
  return response.data
}

/** 暂停工作流 */
export async function pauseWorkflow(id: string): Promise<void> {
  await api.post(`/admin/workflow/pause/${id}`)
}

/** 恢复工作流 */
export async function resumeWorkflow(id: string): Promise<{ task_id: string; status: string }> {
  const response = await api.post<{ task_id: string; status: string }>(`/admin/workflow/resume/${id}`)
  return response.data
}

/** 取消工作流 */
export async function cancelWorkflow(id: string): Promise<void> {
  await api.delete(`/admin/workflow/${id}`)
}

/** 列出所有工作流 */
export async function listWorkflows(): Promise<{ workflows: WorkflowTask[]; has_running: boolean }> {
  const response = await api.get<{ workflows: WorkflowTask[]; has_running: boolean }>('/admin/workflow/list')
  return response.data
}

/** SSE 流式日志 */
export interface WorkflowLogHandlers {
  onLog: (entry: WorkflowLogEntry) => void
  onDone: (status: string) => void
  onError: (message: string) => void
}

export async function streamWorkflowLog(
  taskId: string,
  handlers: WorkflowLogHandlers,
  signal: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  await fetchEventSource(`/api/admin/workflow/log/${taskId}`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token || ''}`,
    },
    signal,
    onmessage(event) {
      if (!event.data) return
      try {
        const data = JSON.parse(event.data)
        if (event.event === 'log') {
          handlers.onLog({ timestamp: data.timestamp, message: data.message })
        } else if (event.event === 'done') {
          handlers.onDone(data.status || 'completed')
        }
      } catch {
        // 忽略解析失败
      }
    },
    onerror(err) {
      if (signal.aborted) {
        throw err
      }
      handlers.onError('日志连接失败')
      throw err
    },
  })
}

// ============================================================
// 知识库管理 API
// ============================================================

import type { KbSummary, KbFileList, CreateKbRequest } from '@/types'

/** 获取知识库列表 */
export async function getKbList(): Promise<{ knowledge_bases: KbSummary[] }> {
  const { data } = await api.get('/admin/knowledge-bases')
  return data
}

/** 获取知识库文件列表（文件浏览器模式，非递归） */
export async function getKbFiles(kbName: string, subPath?: string): Promise<KbFileList> {
  const params = subPath ? { path: subPath } : {}
  const { data } = await api.get(`/admin/knowledge-bases/${encodeURIComponent(kbName)}/files`, { params })
  return data
}

/** 创建空知识库 */
export async function createKnowledgeBase(payload: CreateKbRequest): Promise<{ name: string; message: string }> {
  const { data } = await api.post('/admin/knowledge-bases', payload)
  return data
}

/** 上传 ZIP 创建知识库（支持上传进度回调） */
export async function uploadKbZip(
  file: File,
  name?: string,
  onProgress?: (percent: number) => void,
): Promise<{ name: string; file_count: number; message: string }> {
  const form = new FormData()
  form.append('file', file)
  if (name) form.append('name', name)
  const { data } = await api.post('/admin/knowledge-bases/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    },
  })
  return data
}

/** 删除知识库 */
export async function deleteKnowledgeBase(name: string): Promise<void> {
  await api.delete(`/admin/knowledge-bases/${encodeURIComponent(name)}`)
}

/** 上传文件到知识库 */
export async function uploadKbFile(
  kbName: string,
  file: File,
  subPath?: string,
): Promise<{ file_name: string; rel_path: string; message: string }> {
  const form = new FormData()
  form.append('file', file)
  if (subPath) form.append('path', subPath)
  const { data } = await api.post(
    `/admin/knowledge-bases/${encodeURIComponent(kbName)}/files`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

/** 删除知识库文件 */
export async function deleteKbFile(kbName: string, filePath: string): Promise<void> {
  await api.delete(`/admin/knowledge-bases/${encodeURIComponent(kbName)}/files`, {
    data: { file_path: filePath },
  })
}

/** 下载知识库单个文件 */
export async function downloadKbFile(kbName: string, filePath: string): Promise<void> {
  const response = await api.get(
    `/admin/knowledge-bases/${encodeURIComponent(kbName)}/files/download`,
    { params: { file_path: filePath }, responseType: 'blob' },
  )
  const filename = filePath.split('/').pop() || 'file'
  const url = URL.createObjectURL(new Blob([response.data]))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 下载整个知识库为 ZIP */
export async function downloadKnowledgeBase(kbName: string): Promise<void> {
  const response = await api.get(
    `/admin/knowledge-bases/${encodeURIComponent(kbName)}/download`,
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(new Blob([response.data], { type: 'application/zip' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `${kbName}.zip`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 知识库文件内容预览 */
export interface KbFileContent {
  content: string | null
  truncated: boolean
  size: number
  message?: string
}

export async function getKbFileContent(kbName: string, filePath: string): Promise<KbFileContent> {
  const { data } = await api.get(
    `/admin/knowledge-bases/${encodeURIComponent(kbName)}/files/content`,
    { params: { file_path: filePath } },
  )
  return data
}

export default api