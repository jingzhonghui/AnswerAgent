import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ConversationSummary, Message, FileSelection, FileRef, ThinkingStep } from '@/types'
import {
  getConversations,
  createConversation as apiCreateConversation,
  getConversation,
  deleteConversation as apiDeleteConversation,
  renameConversation as apiRenameConversation,
  streamChat,
} from '@/api'

export const useChatStore = defineStore('chat', () => {
  // 对话列表
  const conversations = ref<ConversationSummary[]>([])
  const activeConversationId = ref<string | null>(null)
  const activeMessages = ref<Message[]>([])
  const isLoading = ref(false)
  const isConversationLoading = ref(false)

  // 深度思考：当前推理步骤列表（实时追加，流式结束后清空）
  const thinkingSteps = ref<ThinkingStep[]>([])

  // 流式状态
  const isStreaming = ref(false)
  const matchedKbs = ref<string[]>([])
  const selectedFiles = ref<FileSelection[]>([])
  let abortController: AbortController | null = null

  // 计算属性
  const hasActiveConversation = () => activeConversationId.value !== null

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
      await loadConversations()
      activeConversationId.value = newConv.id
      activeMessages.value = []
      matchedKbs.value = []
      selectedFiles.value = []
      thinkingSteps.value = []
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
    matchedKbs.value = []
    selectedFiles.value = []
    thinkingSteps.value = []
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
      conversations.value = conversations.value.filter(c => c.id !== id)
      if (activeConversationId.value === id) {
        activeConversationId.value = null
        activeMessages.value = []
        matchedKbs.value = []
        selectedFiles.value = []
        thinkingSteps.value = []
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

  // 设置当前活动对话
  function setActiveConversation(id: string | null): void {
    activeConversationId.value = id
    if (id === null) {
      activeMessages.value = []
      matchedKbs.value = []
      selectedFiles.value = []
      thinkingSteps.value = []
    }
  }

  // 发送消息（SSE 流式）
  async function sendMessage(content: string, mode: string = 'default'): Promise<void> {
    if (!activeConversationId.value) {
      const newId = await createConversation()
      if (!newId) return
    }

    if (!activeConversationId.value) return

    isStreaming.value = true
    abortController = new AbortController()
    matchedKbs.value = []
    selectedFiles.value = []
    thinkingSteps.value = []

    // 添加用户消息到本地
    const userMsg: Message = {
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }
    activeMessages.value.push(userMsg)

    // 添加助手草稿消息（不保留变量引用，每次通过数组索引访问以保证 Vue 响应式）
    activeMessages.value.push({
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    })

    const collectedFiles: FileRef[] = []

    try {
      await streamChat(
        {
          conversation_id: activeConversationId.value,
          message: content,
          mode: mode,
        },
        {
          onKbMatched(kbNames) {
            matchedKbs.value = kbNames
          },
          onFilesSelected(kb, files) {
            selectedFiles.value.push({ kb, files })
            // 构建 FileRef 用于 assistant 消息
            for (const f of files) {
              collectedFiles.push({
                kb_name: kb,
                file_path: f,
                file_name: f.split('/').pop() || f,
              })
            }
            // 通过响应式数组索引更新，触发 Vue 响应式
            const idx = activeMessages.value.length - 1
            if (activeMessages.value[idx]) {
              activeMessages.value[idx].files_used = [...collectedFiles]
            }
          },
          onToken(tokenContent) {
            // 通过响应式数组索引更新，触发 Vue 响应式
            const idx = activeMessages.value.length - 1
            if (activeMessages.value[idx]) {
              activeMessages.value[idx].content += tokenContent
            }
          },
          onAgentThink(_step, thought, tool, toolInput) {
            // 深度思考：记录推理步骤，追加到思考步骤列表
            thinkingSteps.value.push({
              type: 'action',
              thought: thought || '',
              tool: tool || '',
              toolInput: toolInput || '',
            })
          },
          onAgentObserve(_step, result) {
            // 深度思考：记录工具执行结果
            thinkingSteps.value.push({
              type: 'observation',
              result: result || '',
            })
          },
          onDone(_messageId) {
            // 完成
          },
          onError(message) {
            const idx = activeMessages.value.length - 1
            const lastMsg = activeMessages.value[idx]
            if (lastMsg && !lastMsg.content) {
              lastMsg.content = `错误: ${message}`
            }
          },
        },
        abortController.signal,
      )
    } catch {
      const idx = activeMessages.value.length - 1
      const lastMsg = activeMessages.value[idx]
      if (!abortController?.signal.aborted && lastMsg && !lastMsg.content) {
        lastMsg.content = '抱歉，发生了错误，请重试。'
      }
    } finally {
      isStreaming.value = false
      abortController = null
      // 思考步骤保留不立即清空（流式结束后用户仍可查看折叠面板）
      // 刷新对话列表以更新标题和时间
      await loadConversations()
    }
  }

  // 停止生成
  function stopStreaming(): void {
    abortController?.abort()
    isStreaming.value = false
  }

  // 重置所有状态（切换用户时由 authStore.logout() 调用）
  function $reset() {
    conversations.value = []
    activeConversationId.value = null
    activeMessages.value = []
    isLoading.value = false
    isConversationLoading.value = false
    isStreaming.value = false
    matchedKbs.value = []
    selectedFiles.value = []
    thinkingSteps.value = []
    abortController = null
  }

  return {
    // 状态
    conversations,
    activeConversationId,
    activeMessages,
    isLoading,
    isConversationLoading,
    isStreaming,
    matchedKbs,
    selectedFiles,
    thinkingSteps,
    // 计算属性
    hasActiveConversation,
    // 方法
    loadConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    setActiveConversation,
    sendMessage,
    stopStreaming,
    // 重置
    $reset,
  }
})