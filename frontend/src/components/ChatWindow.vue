<script setup lang="ts">
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)

  if (isToday) return '今天'
  if (date.toDateString() === yesterday.toDateString()) return '昨天'

  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric'
  })
}
</script>

<template>
  <main class="chat-window">
    <!-- 空状态 -->
    <div v-if="!chatStore.hasActiveConversation()" class="empty-state">
      <div class="welcome">
        <div class="welcome-logo">
          <span>◆</span>
        </div>
        <h1>Answer Agent</h1>
        <p>基于本地知识库的 AI 问答助手</p>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="chatStore.isConversationLoading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <!-- 消息列表 -->
    <div v-else class="messages-container">
      <div v-if="chatStore.activeMessages.length === 0" class="no-messages">
        <p>发送消息开始对话</p>
      </div>

      <template v-else>
        <div
          v-for="(msg, index) in chatStore.activeMessages"
          :key="index"
          class="message-row"
          :class="msg.role"
        >
          <!-- 日期分隔 -->
          <div
            v-if="index === 0 || formatDate(msg.timestamp) !== formatDate(chatStore.activeMessages[index - 1].timestamp)"
            class="date-divider"
          >
            <span>{{ formatDate(msg.timestamp) }}</span>
          </div>

          <div class="message-content-wrapper">
            <div class="message-avatar">
              <span v-if="msg.role === 'user'">U</span>
              <span v-else>◆</span>
            </div>
            <div class="message-body">
              <div class="message-header-row">
                <span class="message-author">{{ msg.role === 'user' ? '你' : 'Answer Agent' }}</span>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-text">{{ msg.content }}</div>
              <!-- 引用文件 -->
              <div v-if="msg.files_used && msg.files_used.length > 0" class="message-files">
                <span class="files-label">引用:</span>
                <span
                  v-for="file in msg.files_used"
                  :key="file"
                  class="file-tag"
                >
                  {{ file }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </main>
</template>

<style scoped>
.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome {
  text-align: center;
  padding: 40px;
}

.welcome-logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-color);
  border-radius: var(--radius-lg);
  font-size: 28px;
  color: white;
}

.welcome h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.welcome p {
  font-size: 15px;
  color: var(--text-secondary);
  margin: 0;
}

/* 加载中 */
.loading-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 消息容器 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 0;
}

.no-messages {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
  font-size: 14px;
}

.message-row {
  padding: 12px 20%;
}

.message-row.user {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="dark"] .message-row.user {
  background: rgba(255, 255, 255, 0.02);
}

.message-content-wrapper {
  display: flex;
  gap: 12px;
  max-width: 800px;
  margin: 0 auto;
}

.message-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  font-size: 14px;
  color: var(--text-secondary);
}

.message-row.assistant .message-avatar {
  background: var(--accent-color);
  color: white;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.message-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.message-author {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.message-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.message-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 引用文件 */
.message-files {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
}

.files-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.file-tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-size: 12px;
  border-radius: var(--radius-sm);
  font-family: monospace;
}

/* 日期分隔 */
.date-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 24px 0 16px;
}

.date-divider span {
  padding: 4px 12px;
  background: var(--bg-hover);
  color: var(--text-tertiary);
  font-size: 12px;
  border-radius: var(--radius-full);
}

/* 响应式 */
@media (max-width: 1200px) {
  .message-row {
    padding: 12px 10%;
  }
}

@media (max-width: 768px) {
  .message-row {
    padding: 12px 16px;
  }
}
</style>
