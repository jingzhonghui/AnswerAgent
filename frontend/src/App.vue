<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

onMounted(() => {
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark')
  }

  // 页面刷新时从 localStorage 恢复用户信息
  if (authStore.token) {
    authStore.fetchMe()
  }
})
</script>

<template>
  <RouterView />
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
</style>
