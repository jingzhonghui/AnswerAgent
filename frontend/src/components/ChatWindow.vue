<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
const authStore = useAuthStore()
const chatStore = useChatStore()

// 消息列表容器引用和自动滚动逻辑
const messagesContainer = ref<HTMLElement | null>(null)
const userScrolledUp = ref(false)
const SCROLL_THRESHOLD = 60 // 距底部多少像素以内视为"在底部"

function isNearBottom(): boolean {
  const el = messagesContainer.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD
}

function scrollToBottom(smooth = false): void {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
}

function handleScroll(): void {
  if (isNearBottom()) {
    userScrolledUp.value = false
  } else {
    userScrolledUp.value = true
  }
}

// 监听消息内容变化：生成中自动滚动
watch(
  () => chatStore.activeMessages.map(m => m.content),
  () => {
    if (chatStore.isStreaming && !userScrolledUp.value) {
      nextTick(() => scrollToBottom(false))
    }
  },
  { deep: false },
)

// 发送消息时立即滚到底部
watch(
  () => chatStore.activeMessages.length,
  () => {
    if (!userScrolledUp.value) {
      nextTick(() => scrollToBottom(false))
    }
  },
)

// 组件挂载时如有消息则滚到底部
onMounted(() => {
  if (chatStore.activeMessages.length > 0) {
    nextTick(() => scrollToBottom(false))
  }
})

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
          <svg viewBox="0 0 1024 1024" width="40" height="40" fill="white">
            <path d="M231.936 409.6v174.592H161.792V409.6h70.144m0-34.816H161.792c-19.456 0-34.816 15.872-34.816 34.816v174.592c0 18.944 15.872 34.816 34.816 34.816h69.632c19.456 0 34.816-15.872 34.816-34.816V409.6c0.512-18.944-15.36-34.816-34.304-34.816zM860.16 409.6v174.592h-69.632V409.6H860.16m0-34.816h-69.632c-18.944 0-34.816 15.872-34.816 34.816v174.592c0 19.456 15.872 34.816 34.816 34.816H860.16c19.456 0 34.816-15.872 34.816-34.816V409.6c0-18.944-15.36-34.816-34.816-34.816z m-349.184 349.184c38.4 0 69.632 31.232 69.632 69.632s-31.232 69.632-69.632 69.632-69.632-31.232-69.632-69.632 31.232-69.632 69.632-69.632m0-34.816c-57.856 0-104.448 47.104-104.448 104.448 0 57.856 47.104 104.96 104.448 104.96s104.448-47.104 104.448-104.448-46.592-104.96-104.448-104.96zM441.344 374.784H371.2v69.632h69.632V374.784z m209.408 0h-69.632v69.632h69.632V374.784z m-19.456 174.592c-24.064 41.472-68.608 69.632-120.32 69.632s-96.256-28.16-120.32-69.632h-39.424c27.136 61.44 88.064 104.448 159.744 104.448s132.608-43.008 159.744-104.448h-39.424z"/>
            <path d="M215.04 374.784c43.52-121.856 159.232-209.408 295.936-209.408s252.416 87.552 295.936 209.408h37.376c-44.544-141.824-176.64-244.224-333.312-244.224s-288.256 102.912-332.8 244.224H215.04z m577.024 244.224c-36.352 72.704-99.328 129.024-176.128 156.16v37.376c96.768-30.208 175.104-101.376 215.04-193.536h-38.912z"/>
          </svg>
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
    <div v-else ref="messagesContainer" class="messages-container" @scroll="handleScroll">
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

          <!-- 助手消息（左侧） -->
          <div v-if="msg.role === 'assistant'" class="message-content-wrapper assistant">
            <div class="message-avatar assistant-avatar">
              <svg viewBox="0 0 1024 1024" width="18" height="18" fill="currentColor">
                <path d="M231.936 409.6v174.592H161.792V409.6h70.144m0-34.816H161.792c-19.456 0-34.816 15.872-34.816 34.816v174.592c0 18.944 15.872 34.816 34.816 34.816h69.632c19.456 0 34.816-15.872 34.816-34.816V409.6c0.512-18.944-15.36-34.816-34.304-34.816zM860.16 409.6v174.592h-69.632V409.6H860.16m0-34.816h-69.632c-18.944 0-34.816 15.872-34.816 34.816v174.592c0 19.456 15.872 34.816 34.816 34.816H860.16c19.456 0 34.816-15.872 34.816-34.816V409.6c0-18.944-15.36-34.816-34.816-34.816z m-349.184 349.184c38.4 0 69.632 31.232 69.632 69.632s-31.232 69.632-69.632 69.632-69.632-31.232-69.632-69.632 31.232-69.632 69.632-69.632m0-34.816c-57.856 0-104.448 47.104-104.448 104.448 0 57.856 47.104 104.96 104.448 104.96s104.448-47.104 104.448-104.448-46.592-104.96-104.448-104.96zM441.344 374.784H371.2v69.632h69.632V374.784z m209.408 0h-69.632v69.632h69.632V374.784z m-19.456 174.592c-24.064 41.472-68.608 69.632-120.32 69.632s-96.256-28.16-120.32-69.632h-39.424c27.136 61.44 88.064 104.448 159.744 104.448s132.608-43.008 159.744-104.448h-39.424z"/>
                <path d="M215.04 374.784c43.52-121.856 159.232-209.408 295.936-209.408s252.416 87.552 295.936 209.408h37.376c-44.544-141.824-176.64-244.224-333.312-244.224s-288.256 102.912-332.8 244.224H215.04z m577.024 244.224c-36.352 72.704-99.328 129.024-176.128 156.16v37.376c96.768-30.208 175.104-101.376 215.04-193.536h-38.912z"/>
              </svg>
            </div>
            <div class="message-body assistant">
              <div class="message-author-row">
                <span class="message-author">Answer Agent</span>
                <span class="message-time">{{ formatTime(getMsgTimestamp(msg)) }}</span>
              </div>
              <div class="message-bubble assistant-bubble">
                <div
                  class="message-text markdown-body"
                  v-html="renderMarkdown(msg.content)"
                />
                <span
                  v-if="chatStore.isStreaming && index === chatStore.activeMessages.length - 1"
                  class="streaming-cursor"
                >▌</span>
              </div>
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

          <!-- 用户消息（右侧） -->
          <div v-else class="message-content-wrapper user">
            <div class="message-body user">
              <div class="message-bubble user-bubble">
                <div class="message-text">
                  {{ msg.content }}
                </div>
              </div>
            </div>
            <div class="message-avatar user-avatar">
              <span>{{ authStore.user?.username?.charAt(0).toUpperCase() || 'U' }}</span>
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

/* ===== 气泡对话布局 ===== */

/* 消息行：左对齐（助手）/ 右对齐（用户） */
.message-row {
  padding: 6px 20%;
}

.message-content-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 800px;
  margin: 0 auto;
}

/* 用户消息 -> 右对齐 */
.message-content-wrapper.user {
  justify-content: flex-end;
}

/* 助手消息 -> 左对齐 */
.message-content-wrapper.assistant {
  justify-content: flex-start;
}

/* 头像 - 圆形 */
.message-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 600;
  position: sticky;
  top: 0;
}

.assistant-avatar {
  background: var(--accent-color);
  color: white;
}

.user-avatar {
  background: #10a37f;
  color: white;
}

/* 消息体容器 */
.message-body {
  display: flex;
  flex-direction: column;
  max-width: 75%;
  min-width: 0;
}

.message-body.assistant {
  align-items: flex-start;
}

.message-body.user {
  align-items: flex-end;
}

/* 助手名称行 */
.message-author-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  padding-left: 4px;
}

.message-author {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* 气泡 */
.message-bubble {
  padding: 10px 16px;
  line-height: 1.6;
  word-break: break-word;
}

.assistant-bubble {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: 4px 16px 16px 16px;
  color: var(--text-primary);
}

.user-bubble {
  background: var(--accent-color);
  border-radius: 16px 4px 16px 16px;
  color: #ffffff;
}

.message-text {
  font-size: 15px;
  white-space: pre-wrap;
}

.user-bubble .message-text {
  color: #ffffff;
}

/* 流式光标 */
.streaming-cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent-color);
  font-size: 15px;
  font-weight: bold;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* markdown 渲染样式 */
.assistant-bubble .markdown-body {
  white-space: normal;
}

.assistant-bubble .markdown-body :deep(p) {
  margin: 0 0 8px;
}

.assistant-bubble .markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-bubble .markdown-body :deep(code) {
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

[data-theme="dark"] .assistant-bubble .markdown-body :deep(code) {
  background: rgba(255, 255, 255, 0.1);
}

.assistant-bubble .markdown-body :deep(pre) {
  margin: 8px 0;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.assistant-bubble .markdown-body :deep(pre code) {
  display: block;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.5;
  background: var(--bg-primary) !important;
}

.assistant-bubble .markdown-body :deep(ul),
.assistant-bubble .markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.assistant-bubble .markdown-body :deep(li) {
  margin: 2px 0;
}

.assistant-bubble .markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--accent-color);
  color: var(--text-secondary);
}

.assistant-bubble .markdown-body :deep(a) {
  color: var(--accent-color);
  text-decoration: none;
}

.assistant-bubble .markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.assistant-bubble .markdown-body :deep(strong) {
  font-weight: 600;
}

/* 引用文件 */
.message-files {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 4px 0;
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
    padding: 6px 10%;
  }
  .kb-match-status {
    padding: 12px 10%;
  }
}

@media (max-width: 768px) {
  .message-row {
    padding: 6px 16px;
  }
  .kb-match-status {
    padding: 12px 16px;
  }

  .message-body {
    max-width: 85%;
  }
}
</style>