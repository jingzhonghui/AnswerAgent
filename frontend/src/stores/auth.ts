import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import { apiLogin, apiRegister, apiGetMe } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  const user = ref<{ id: string; username: string } | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(accessToken: string, userInfo: { id: string; username: string }) {
    token.value = accessToken
    user.value = userInfo
    localStorage.setItem('access_token', accessToken)
  }

  async function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('access_token')

    // 重置聊天状态，避免切换用户时显示旧数据
    try {
      const { useChatStore } = await import('@/stores/chat')
      const chatStore = useChatStore()
      chatStore.$reset()
    } catch {
      // Chat store 可能尚未初始化
    }

    router.push('/login')
  }

  async function login(username: string, password: string): Promise<string | null> {
    const result = await apiLogin(username, password)
    setAuth(result.access_token, result.user)
    return null
  }

  async function register(username: string, password: string): Promise<string | null> {
    const result = await apiRegister(username, password)
    setAuth(result.access_token, result.user)
    return null
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return
    try {
      const userInfo = await apiGetMe()
      user.value = userInfo
    } catch {
      // token 无效，清除登录状态
      logout()
    }
  }

  return {
    user,
    token,
    isLoggedIn,
    setAuth,
    logout,
    login,
    register,
    fetchMe,
  }
})