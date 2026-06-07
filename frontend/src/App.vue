<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatWindow from '@/components/ChatWindow.vue'
import InputBar from '@/components/InputBar.vue'

const isDark = ref(false)
const sidebarCollapsed = ref(false)

onMounted(() => {
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'dark') {
    isDark.value = true
    document.documentElement.setAttribute('data-theme', 'dark')
  }

  const savedCollapsed = localStorage.getItem('sidebarCollapsed')
  if (savedCollapsed === '1') {
    sidebarCollapsed.value = true
  }
})

function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.setAttribute('data-theme', 'dark')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

function collapseSidebar() {
  sidebarCollapsed.value = true
  localStorage.setItem('sidebarCollapsed', '1')
}

function expandSidebar() {
  sidebarCollapsed.value = false
  localStorage.setItem('sidebarCollapsed', '0')
}
</script>

<template>
  <div class="app">
    <Transition name="sidebar">
      <ConversationSidebar
        v-if="!sidebarCollapsed"
        :is-dark="isDark"
        @collapse="collapseSidebar"
        @toggle-theme="toggleTheme"
      />
    </Transition>
    <main class="main">
      <button
        v-if="sidebarCollapsed"
        class="expand-sidebar-btn"
        @click="expandSidebar"
        title="展开侧边栏"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="4" width="18" height="16" rx="2"/>
          <path d="M9 4v16"/>
          <path d="M13 10l3 2-3 2"/>
        </svg>
      </button>
      <ChatWindow />
      <InputBar />
    </main>
  </div>
</template>

<style>
/* DeepSeek 风格变量 */
:root {
  --bg-primary: #ffffff;
  --bg-sidebar: #f9f9f9;
  --bg-hover: #f0f0f0;
  --bg-active: #e8e8e8;
  --text-primary: #1a1a1a;
  --text-secondary: #666666;
  --text-tertiary: #999999;
  --accent-color: #4e6ef2;
  --accent-hover: #4662d9;
  --border-color: #e5e5e5;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-full: 9999px;
}

[data-theme="dark"] {
  --bg-primary: #1a1a1a;
  --bg-sidebar: #151515;
  --bg-hover: #252525;
  --bg-active: #333333;
  --text-primary: #f0f0f0;
  --text-secondary: #b0b0b0;
  --text-tertiary: #666666;
  --accent-color: #5b7bf5;
  --accent-hover: #6b8bf6;
  --border-color: #2a2a2a;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.3);
}

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
  -webkit-font-smoothing: antialiased;
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

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* 滚动条 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
}

:hover::-webkit-scrollbar-thumb {
  background: var(--border-color);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 浮动展开侧边栏按钮 */
.expand-sidebar-btn {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 10;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: var(--shadow-sm);
}

.expand-sidebar-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent-color);
}

.expand-sidebar-btn svg {
  width: 18px;
  height: 18px;
}


/* 侧边栏过渡动画 */
.sidebar-enter-active,
.sidebar-leave-active {
  transition: width 0.2s ease, opacity 0.2s ease, margin-left 0.2s ease;
  overflow: hidden;
}

.sidebar-enter-from,
.sidebar-leave-to {
  width: 0 !important;
  min-width: 0 !important;
  margin-left: -1px;
  opacity: 0;
}
</style>
