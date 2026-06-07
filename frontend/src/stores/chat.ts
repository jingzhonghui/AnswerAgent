import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ConversationSummary, Message } from '@/types'
import {
  getConversations,
  createConversation as apiCreateConversation,
  getConversation,
  deleteConversation as apiDeleteConversation,
  renameConversation as apiRenameConversation
} from '@/api'

export const useChatStore = defineStore('chat', () => {
  // 状态
  const conversations = ref<ConversationSummary[]>([])
  const activeConversationId = ref<string | null>(null)
  const activeMessages = ref<Message[]>([])
  const isLoading = ref(false)
  const isConversationLoading = ref(false)

  // 计算属性
  const hasActiveConversation = () => activeConversationId.value !== null

  const activeConversation = () => {
    return conversations.value.find(c => c.id === activeConversationId.value)
  }

  // 加载对话列表
  async function loadConversations(): Promise<void> {
    isLoading.value = true
    try {
      const data = await getConversations()
      conversations.value = data
    } catch (error) {
      console.error('Failed to load conversations:', error)
      conversations.value = []
    } finally {
      isLoading.value = false
    }
  }

  // 新建对话
  async function createConversation(): Promise<string | null> {
    try {
      const newConv = await apiCreateConversation()
      // 刷新列表以包含新对话
      await loadConversations()
      // 选中新创建的对话
      activeConversationId.value = newConv.id
      activeMessages.value = []
      return newConv.id
    } catch (error) {
      console.error('Failed to create conversation:', error)
      return null
    }
  }

  // 选择对话并加载详情
  async function selectConversation(id: string): Promise<void> {
    if (activeConversationId.value === id) return

    isConversationLoading.value = true
    try {
      const conversation = await getConversation(id)
      activeConversationId.value = id
      activeMessages.value = conversation.messages
    } catch (error) {
      console.error('Failed to load conversation:', error)
      activeMessages.value = []
    } finally {
      isConversationLoading.value = false
    }
  }

  // 删除对话
  async function deleteConversation(id: string): Promise<boolean> {
    try {
      await apiDeleteConversation(id)
      // 从本地列表中移除
      conversations.value = conversations.value.filter(c => c.id !== id)
      // 如果删除的是当前选中的对话，清空选中状态
      if (activeConversationId.value === id) {
        activeConversationId.value = null
        activeMessages.value = []
      }
      return true
    } catch (error) {
      console.error('Failed to delete conversation:', error)
      return false
    }
  }

  // 重命名对话
  async function renameConversation(id: string, title: string): Promise<boolean> {
    try {
      await apiRenameConversation(id, title)
      // 更新本地列表中的标题
      const conv = conversations.value.find(c => c.id === id)
      if (conv) {
        conv.title = title
      }
      return true
    } catch (error) {
      console.error('Failed to rename conversation:', error)
      return false
    }
  }

  // 设置当前活动对话（不重新加载）
  function setActiveConversation(id: string | null): void {
    activeConversationId.value = id
    if (id === null) {
      activeMessages.value = []
    }
  }

  return {
    // 状态
    conversations,
    activeConversationId,
    activeMessages,
    isLoading,
    isConversationLoading,
    // 计算属性
    hasActiveConversation,
    activeConversation,
    // 方法
    loadConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    setActiveConversation
  }
})
