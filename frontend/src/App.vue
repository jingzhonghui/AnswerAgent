<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatWindow from '@/components/ChatWindow.vue'

const isDark = ref(false)

// 初始化主题
onMounted(() => {
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'dark') {
    isDark.value = true
    document.documentElement.setAttribute('data-theme', 'dark')
  }
})

// 切换主题
function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.setAttribute('data-theme', 'dark')
    localStorage.setItem('theme', 'dark')
  } else {
    document.documentElement.removeAttribute('data-theme')
    localStorage.setItem('theme', 'light')
  }
}
</script>

<template>
  <div class="app">
    <!-- 侧边栏 -->
    <ConversationSidebar />

    <!-- 主聊天区域 -->
    <div class="main-area">
      <!-- 顶部工具栏 -->
      <header class="top-bar">
        <button class="theme-btn" @click="toggleTheme">
          {{ isDark ? '☀️' : '🌙' }}
        </button>
      </header>

      <!-- 聊天窗口 -->
      <ChatWindow />
    </div>
  </div>
</template>

<style>
/* CSS 变量定义 */
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --bg-sidebar: #f0f0f0;
  --text-primary: #1a1a1a;
  --text-secondary: #666666;
  --accent-color: #4f6ef7;
  --border-color: #e0e0e0;
  --hover-bg: #e8e8e8;
  --message-user-bg: #4f6ef7;
  --message-ai-bg: #f0f0f0;
  --code-bg: #f6f8fa;
}

[data-theme="dark"] {
  --bg-primary: #1a1a1a;
  --bg-secondary: #242424;
  --bg-sidebar: #1e1e1e;
  --text-primary: #e8e8e8;
  --text-secondary: #999999;
  --accent-color: #6b84f8;
  --border-color: #333333;
  --hover-bg: #2a2a2a;
  --message-user-bg: #3d5af1;
  --message-ai-bg: #2a2a2a;
  --code-bg: #2d2d2d;
}

/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.5;
}

#app {
  height: 100vh;
}

.app {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
  overflow: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.top-bar {
  height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  background: var(--bg-primary);
}

.theme-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.theme-btn:hover {
  background: var(--hover-bg);
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>
