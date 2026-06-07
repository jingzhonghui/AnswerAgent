import axios, { type AxiosInstance } from 'axios'
import type {
  ConversationSummary,
  Conversation,
  CreateConversationResponse,
  RenameConversationRequest
} from '@/types'

// axios 实例配置
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - 错误处理
api.interceptors.response.use(
  (response) => response,
  (error) => {
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
export async function createConversation(): Promise<CreateConversationResponse> {
  const response = await api.post<CreateConversationResponse>('/conversations')
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

export default api
