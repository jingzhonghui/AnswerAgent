<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Shield } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

onMounted(() => {
  // 恢复主题（与 App.vue 一致）
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark')
  }

  // 如果已是管理员，直接跳转后台
  if (authStore.token && authStore.isAdmin) {
    router.replace('/admin')
    return
  }
  // 如果已登录但不是管理员，跳回聊天页
  if (authStore.token && !authStore.isAdmin) {
    router.replace('/chat')
  }
})

async function handleLogin() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  try {
    await authStore.login(username.value.trim(), password.value)
    // 登录成功后检查是否为管理员
    if (!authStore.isAdmin) {
      error.value = '此账号无管理员权限'
      // 直接清状态，不调用 logout()（logout 会跳转到 /login）
      authStore.token = null
      authStore.user = null
      localStorage.removeItem('access_token')
      return
    }
    router.push('/admin')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '登录失败，请重试'
    error.value = typeof detail === 'string' ? detail : '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="admin-login-page">
    <div class="login-card">
      <div class="card-header">
        <div class="shield-icon">
          <Shield :size="28" />
        </div>
        <h1>管理后台</h1>
        <p class="subtitle">Answer Agent Administration</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">管理员账号</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="请输入管理员账号"
            autocomplete="username"
            :disabled="loading"
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>

        <div v-if="error" class="error-message">
          <span class="error-icon">⚠</span>
          {{ error }}
        </div>

        <button type="submit" class="login-btn" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          <span v-else>进入后台</span>
        </button>
      </form>

      <div class="card-footer">
        <router-link to="/chat" class="back-link">← 返回 Answer Agent</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-primary);
  position: relative;
  overflow: hidden;
}

.login-card {
  position: relative;
  width: 100%;
  max-width: 400px;
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 44px 40px 36px;
  box-shadow: var(--shadow-md);
}

.card-header {
  text-align: center;
  margin-bottom: 36px;
}

.shield-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4e6ef2, #7c3aed);
  color: white;
  border-radius: 14px;
  margin: 0 auto 16px;
}

.card-header h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.subtitle {
  font-size: 12px;
  color: var(--text-tertiary);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.form-group input {
  padding: 11px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.form-group input:focus {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(78, 110, 242, 0.15);
}

.form-group input::placeholder {
  color: var(--text-tertiary);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-sm);
  color: #ef4444;
  font-size: 13px;
}

.error-icon {
  font-size: 14px;
}

.login-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  padding: 0 24px;
  background: var(--accent-color);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  letter-spacing: 0.5px;
}

.login-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.25);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.card-footer {
  margin-top: 28px;
  text-align: center;
}

.back-link {
  font-size: 13px;
  color: var(--text-tertiary);
  text-decoration: none;
  transition: color 0.15s;
}

.back-link:hover {
  color: var(--text-secondary);
}
</style>