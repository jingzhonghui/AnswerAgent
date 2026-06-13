<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const inputText = ref('')
const isDeepMode = ref(false)

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.isStreaming) return

  inputText.value = ''
  await chatStore.sendMessage(text, isDeepMode.value ? 'deep' : 'default')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function stopStreaming() {
  chatStore.stopStreaming()
}
</script>

<template>
  <div class="input-bar">
    <div class="input-wrapper">
      <!-- 输入框 -->
      <div class="input-container">
        <textarea
          v-model="inputText"
          class="input-textarea"
          :placeholder="chatStore.isStreaming ? '生成中...' : '给 Answer Agent 发送消息'"
          :disabled="chatStore.isStreaming"
          rows="1"
          @keydown="handleKeydown"
        />

        <!-- 工具栏 -->
        <div class="input-toolbar">
          <div class="toolbar-left">
            <button
              v-if="chatStore.deepModelEnabled"
              class="toolbar-btn"
              :class="{ active: isDeepMode }"
              @click="isDeepMode = !isDeepMode"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
              </svg>
              <span>深度思考</span>
            </button>
          </div>

          <div class="toolbar-right">
            <!-- 停止按钮 -->
            <button
              v-if="chatStore.isStreaming"
              class="send-btn stop"
              @click="stopStreaming"
              title="停止生成"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
              </svg>
            </button>

            <!-- 发送按钮 -->
            <button
              v-else
              class="send-btn"
              :disabled="!inputText.trim()"
              @click="handleSend"
              title="发送"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 提示文字 -->
      <div class="input-hint">
        内容由 AI 生成，请仔细甄别
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-bar {
  padding: 16px 20% 24px;
  background: var(--bg-primary);
}

.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
}

.input-container {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-container:focus-within {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(78, 110, 242, 0.1);
}

.input-textarea {
  width: 100%;
  padding: 14px 16px;
  background: transparent;
  border: none;
  resize: none;
  font-size: 16px;
  line-height: 1.5;
  color: var(--text-primary);
  font-family: inherit;
  outline: none;
  max-height: 200px;
  min-height: 24px;
}

.input-textarea::placeholder {
  color: var(--text-tertiary);
}

.input-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.toolbar-btn.active {
  background: rgba(78, 110, 242, 0.1);
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.toolbar-btn svg {
  width: 14px;
  height: 14px;
}

.toolbar-right {
  display: flex;
  align-items: center;
}

.send-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-color);
  border: none;
  border-radius: var(--radius-full);
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  background: var(--border-color);
  cursor: not-allowed;
}

.send-btn.stop {
  background: #ef4444;
}

.send-btn.stop:hover {
  background: #dc2626;
}

.send-btn svg {
  width: 16px;
  height: 16px;
}

.input-hint {
  text-align: center;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 响应式 */
@media (max-width: 1200px) {
  .input-bar {
    padding: 16px 10% 24px;
  }
}

@media (max-width: 768px) {
  .input-bar {
    padding: 12px 16px 16px;
  }
}
</style>
