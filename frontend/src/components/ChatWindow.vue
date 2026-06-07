<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { useChatStore } from '@/stores/chat'
const chatStore = useChatStore()

// markdown-it 实例
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return '<pre class="hljs"><code>' +
          hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
          '</code></pre>'
      } catch {
        // fall through
      }
    }
    return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'
  },
})

function renderMarkdown(text: string): string {
  return md.render(text)
}

function formatTime(timestamp?: string): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDate(timestamp?: string): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)

  if (isToday) return '今天'
  if (date.toDateString() === yesterday.toDateString()) return '昨天'

  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
  })
}

// 获取消息时间戳（兼容 timestamp 和 created_at）
function getMsgTimestamp(msg: { timestamp?: string; created_at?: string }): string {
  return msg.timestamp || msg.created_at || ''
}

// 是否显示知识库匹配状态
const showKbStatus = computed(() => {
  return chatStore.isStreaming && chatStore.matchedKbs.length > 0
})
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
      <!-- 知识库匹配状态 -->
      <div v-if="showKbStatus" class="kb-match-status">
        <span class="kb-match-label">匹配知识库:</span>
        <span
          v-for="kb in chatStore.matchedKbs"
          :key="kb"
          class="kb-badge"
        >
          {{ kb }}
        </span>
      </div>

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
            v-if="index === 0 || formatDate(getMsgTimestamp(msg)) !== formatDate(getMsgTimestamp(chatStore.activeMessages[index - 1]))"
            class="date-divider"
          >
            <span>{{ formatDate(getMsgTimestamp(msg)) }}</span>
          </div>

          <div class="message-content-wrapper">
            <div class="message-avatar">
              <span v-if="msg.role === 'user'">U</span>
              <span v-else>◆</span>
            </div>
            <div class="message-body">
              <div class="message-header-row">
                <span class="message-author">
                  {{ msg.role === 'user' ? '你' : 'Answer Agent' }}
                </span>
                <span class="message-time">{{ formatTime(getMsgTimestamp(msg)) }}</span>
              </div>

              <!-- 用户消息：纯文本 -->
              <div v-if="msg.role === 'user'" class="message-text">
                {{ msg.content }}
              </div>

              <!-- 助手消息：markdown 渲染 -->
              <div
                v-else
                class="message-text markdown-body"
                v-html="renderMarkdown(msg.content)"
              />

              <!-- 流式光标 -->
              <span
                v-if="msg.role === 'assistant' && chatStore.isStreaming && index === chatStore.activeMessages.length - 1"
                class="streaming-cursor"
              >▌</span>

              <!-- 引用文件 -->
              <div
                v-if="msg.files_used && msg.files_used.length > 0"
                class="message-files"
              >
                <span class="files-label">参考文件:</span>
                <span
                  v-for="file in msg.files_used"
                  :key="file.file_path"
                  class="file-tag"
                >
                  {{ file.file_path }}
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

/* 知识库匹配状态 */
.kb-match-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20%;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.kb-match-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.kb-badge {
  display: inline-block;
  padding: 4px 10px;
  background: rgba(78, 110, 242, 0.1);
  color: var(--accent-color);
  font-size: 12px;
  border-radius: var(--radius-full);
  border: 1px solid rgba(78, 110, 242, 0.2);
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

/* 流式光标 */
.streaming-cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent-color);
  font-size: 15px;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* markdown 渲染样式 */
.markdown-body {
  white-space: normal;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  background: var(--bg-hover);
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

.markdown-body :deep(pre) {
  margin: 8px 0;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  display: block;
  padding: 12px 16px;
  background: var(--bg-sidebar);
  font-size: 13px;
  line-height: 1.5;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--accent-color);
  color: var(--text-secondary);
}

.markdown-body :deep(a) {
  color: var(--accent-color);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(strong) {
  font-weight: 600;
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
  .kb-match-status {
    padding: 12px 10%;
  }
}

@media (max-width: 768px) {
  .message-row {
    padding: 12px 16px;
  }
  .kb-match-status {
    padding: 12px 16px;
  }
}
</style>