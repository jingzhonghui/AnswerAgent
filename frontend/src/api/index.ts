import axios, { type AxiosInstance } from 'axios'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import type {
  ConversationSummary,
  Conversation,
  CreateConversationResponse,
  RenameConversationRequest,
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
      window.location.href = '/#/login'
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

// SSE 流式问答 -> POST /api/chat/stream
export interface StreamChatHandlers {
  onKbMatched: (kbNames: string[]) => void
  onFilesSelected: (kb: string, files: string[]) => void
  onToken: (content: string) => void
  onDone: (messageId: string) => void
  onError: (message: string) => void
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
            handlers.onDone(data.message_id || '')
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
// Auth API
// ============================================================

export interface AuthUser {
  id: string
  username: string
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

export default api