<script setup lang="ts">
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

// 格式化时间
function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 格式化日期
function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return '今天'
  }

  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) {
    return '昨天'
  }

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
      <div class="welcome-content">
        <h2>欢迎使用 Answer Agent</h2>
        <p>基于本地知识库的 AI 问答助手</p>
        <div class="hints">
          <div class="hint-item">
            <span class="hint-icon">💬</span>
            <span>在左侧选择或新建对话开始交流</span>
          </div>
          <div class="hint-item">
            <span class="hint-icon">📚</span>
            <span>系统会自动匹配相关知识库</span>
          </div>
          <div class="hint-item">
            <span class="hint-icon">⚡</span>
            <span>支持流式输出，实时查看回答</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="chatStore.isConversationLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载对话中...</span>
    </div>

    <!-- 消息列表 -->
    <div v-else class="messages-container">
      <div class="messages-header">
        <h2 class="conversation-title">
          {{ chatStore.activeConversation()?.title || '未命名对话' }}
        </h2>
      </div>

      <div class="messages-list">
        <template v-if="chatStore.activeMessages.length === 0">
          <div class="no-messages">
            <p>暂无消息，开始发送第一条消息吧</p>
          </div>
        </template>

        <template v-else>
          <div
            v-for="(msg, index) in chatStore.activeMessages"
            :key="index"
            class="message-wrapper"
            :class="msg.role"
          >
            <!-- 日期分隔线 -->
            <div
              v-if="index === 0 || formatDate(msg.timestamp) !== formatDate(chatStore.activeMessages[index - 1].timestamp)"
              class="date-divider"
            >
              <span>{{ formatDate(msg.timestamp) }}</span>
            </div>

            <div class="message">
              <div class="message-header">
                <span class="message-role">
                  {{ msg.role === 'user' ? '你' : '助手' }}
                </span>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-content">
                {{ msg.content }}
              </div>
              <!-- 知识库引用 -->
              <div v-if="msg.kb_names && msg.kb_names.length > 0" class="message-kb-tags">
                <span
                  v-for="kb in msg.kb_names"
                  :key="kb"
                  class="kb-tag"
                >
                  {{ kb }}
                </span>
              </div>
              <!-- 引用文件 -->
              <div v-if="msg.files_used && msg.files_used.length > 0" class="message-files">
                <span class="files-label">参考文件:</span>
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
        </template>
      </div>
    </div>
  </main>
</template>

<style scoped>
.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.welcome-content {
  text-align: center;
  max-width: 480px;
}

.welcome-content h2 {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

.welcome-content > p {
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0 0 32px 0;
}

.hints {
  display: flex;
  flex-direction: column;
  gap: 16px;
  text-align: left;
}

.hint-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.hint-icon {
  font-size: 18px;
}

/* 加载中 */
.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 消息容器 */
.messages-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.conversation-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.messages-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.no-messages {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 14px;
}

/* 消息样式 */
.message-wrapper {
  margin-bottom: 24px;
}

.message-wrapper.user {
  display: flex;
  justify-content: flex-end;
}

.message-wrapper.assistant {
  display: flex;
  justify-content: flex-start;
}

.message {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--bg-secondary);
}

.message-wrapper.user .message {
  background: var(--accent-color);
  color: white;
}

.message-wrapper.assistant .message {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.message-wrapper.user .message-header {
  color: rgba(255, 255, 255, 0.8);
}

.message-wrapper.assistant .message-header {
  color: var(--text-secondary);
}

.message-role {
  font-weight: 500;
}

.message-time {
  opacity: 0.7;
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 知识库标签 */
.message-kb-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.kb-tag {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(79, 110, 247, 0.1);
  color: var(--accent-color);
  font-size: 11px;
  border-radius: 4px;
  border: 1px solid rgba(79, 110, 247, 0.2);
}

.message-wrapper.user .kb-tag {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border-color: rgba(255, 255, 255, 0.3);
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

.message-wrapper.user .message-files {
  border-top-color: rgba(255, 255, 255, 0.2);
}

.files-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.message-wrapper.user .files-label {
  color: rgba(255, 255, 255, 0.7);
}

.file-tag {
  display: inline-block;
  padding: 2px 6px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 11px;
  border-radius: 3px;
  font-family: monospace;
}

.message-wrapper.user .file-tag {
  background: rgba(255, 255, 255, 0.15);
  color: white;
}

/* 日期分隔线 */
.date-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 24px 0;
  position: relative;
}

.date-divider::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border-color);
}

.date-divider span {
  position: relative;
  padding: 0 12px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 12px;
  z-index: 1;
}
</style>
