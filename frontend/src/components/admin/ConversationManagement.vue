<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { getAdminConversations, getAdminConversation, deleteAdminConversation, exportConversation } from '@/api'
import type { AdminConversationSummary, Conversation } from '@/types'

const conversations = ref<AdminConversationSummary[]>([])
const isLoading = ref(false)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const searchQuery = ref('')
const selectedConv = ref<Conversation | null>(null)
const isViewingDetail = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  await loadConversations()
})

async function loadConversations() {
  isLoading.value = true
  try {
    const params: { search?: string } = {}
    if (searchQuery.value.trim()) {
      params.search = searchQuery.value.trim()
    }
    conversations.value = await getAdminConversations(params)
  } catch {
    showMessage('加载对话列表失败', 'error')
  } finally {
    isLoading.value = false
  }
}

watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadConversations(), 300)
})

async function viewConversation(id: string) {
  isViewingDetail.value = true
  try {
    selectedConv.value = await getAdminConversation(id)
  } catch {
    showMessage('加载对话详情失败', 'error')
    isViewingDetail.value = false
  }
}

function closeDetail() {
  selectedConv.value = null
  isViewingDetail.value = false
}

async function handleDelete(conv: AdminConversationSummary) {
  if (!confirm(`确定要删除 "${conv.title}" 吗？此操作不可撤销。`)) return

  try {
    await deleteAdminConversation(conv.id)
    conversations.value = conversations.value.filter(c => c.id !== conv.id)
    showMessage('已删除对话', 'success')
  } catch {
    showMessage('删除失败', 'error')
  }
}

async function handleExport(conv: AdminConversationSummary) {
  try {
    const safeTitle = conv.title.replace(/[/\\:*?"<>|]/g, '_')
    await exportConversation(conv.id, `${safeTitle}.md`)
    showMessage('导出成功', 'success')
  } catch {
    showMessage('导出失败', 'error')
  }
}

function showMessage(msg: string, type: 'success' | 'error') {
  message.value = msg
  messageType.value = type
  setTimeout(() => { message.value = '' }, 3000)
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>会话管理</h1>
        <p class="subtitle">共 {{ conversations.length }} 个对话</p>
      </div>
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="搜索对话标题..."
        />
      </div>
    </div>

    <div v-if="message" class="message" :class="messageType">
      {{ message }}
    </div>

    <!-- 对话详情面板 -->
    <div v-if="isViewingDetail && selectedConv" class="detail-panel">
      <div class="detail-header">
        <h3>{{ selectedConv.title }}</h3>
        <button class="btn-close" @click="closeDetail">✕</button>
      </div>
      <div class="detail-meta">
        <span>创建: {{ formatDate(selectedConv.created_at) }}</span>
        <span>更新: {{ formatDate(selectedConv.updated_at) }}</span>
        <span>{{ selectedConv.messages.length }} 条消息</span>
      </div>
      <div class="detail-messages">
        <div
          v-for="(msg, idx) in selectedConv.messages"
          :key="idx"
          class="detail-msg"
          :class="msg.role"
        >
          <div class="msg-role">{{ msg.role === 'user' ? '👤 用户' : '🤖 助手' }}</div>
          <div class="msg-content">{{ msg.content }}</div>
          <div v-if="msg.thinking_steps?.length" class="msg-thinking-badge">
            💭 {{ msg.thinking_steps.length }} 个深度思考步骤
          </div>
        </div>
      </div>
    </div>

    <!-- 表格视图 -->
    <div v-if="!isViewingDetail">
      <div v-if="isLoading" class="loading">加载中...</div>
      <div v-else-if="conversations.length === 0" class="empty">暂无对话</div>
      <table v-else class="conv-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>所属用户</th>
            <th>消息数</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="conv in conversations" :key="conv.id">
            <td class="title-cell">{{ conv.title }}</td>
            <td>
              <span class="user-tag">{{ conv.username || '(无主)' }}</span>
            </td>
            <td>{{ conv.message_count }}</td>
            <td class="date-cell">{{ formatDate(conv.updated_at) }}</td>
            <td class="actions-cell">
              <button class="btn-sm" @click="viewConversation(conv.id)">查看</button>
              <button class="btn-sm" @click="handleExport(conv)">导出</button>
              <button class="btn-sm btn-danger" @click="handleDelete(conv)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page {
  width: 100%;
  padding: 0 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

.search-box {
  width: 280px;
}

.search-input {
  width: 100%;
  padding: 8px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.message {
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 20px;
}

.message.success {
  background: #ecfdf5;
  color: #065f46;
}

.message.error {
  background: #fef2f2;
  color: #991b1b;
}

[data-theme="dark"] .message.success {
  background: #064e3b;
  color: #a7f3d0;
}

[data-theme="dark"] .message.error {
  background: #7f1d1d;
  color: #fecaca;
}

.loading {
  color: var(--text-tertiary);
  font-size: 14px;
}

.empty {
  color: var(--text-tertiary);
  font-size: 14px;
  text-align: center;
  padding: 40px;
}

/* 对话表格 */
.conv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.conv-table th {
  text-align: left;
  padding: 10px 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.conv-table td {
  text-align: center;
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.title-cell {
  color: var(--text-primary);
  font-weight: 500;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.date-cell {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.actions-cell {
  display: flex;
  gap: 6px;
}

.btn-sm {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.btn-sm:hover {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.btn-danger {
  color: #dc2626;
  border-color: #fecaca;
}

.btn-danger:hover {
  background: #fef2f2;
  border-color: #dc2626;
}

[data-theme="dark"] .btn-danger {
  color: #fca5a5;
  border-color: #7f1d1d;
}

[data-theme="dark"] .btn-danger:hover {
  background: #7f1d1d;
}

/* 详情面板 */
.detail-panel {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.detail-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.btn-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.detail-meta {
  display: flex;
  gap: 20px;
  padding: 10px 20px;
  font-size: 12px;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.detail-messages {
  padding: 16px 20px;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-msg {
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
}

.detail-msg.assistant {
  background: var(--bg-sidebar);
}

.msg-role {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.msg-content {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-thinking-badge {
  margin-top: 8px;
  font-size: 11px;
  color: var(--accent-color);
}
</style>