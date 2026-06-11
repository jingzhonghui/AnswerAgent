import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/login',
    name: 'AdminLogin',
    component: () => import('@/views/AdminLoginView.vue'),
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/chat',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

/** 从 JWT 中解码 is_admin（不做签名验证，仅用于 UI 判断） */
function checkIsAdmin(): boolean {
  const token = localStorage.getItem('access_token')
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return !!payload.is_admin
  } catch {
    return false
  }
}

// 全局导航守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')

  if (to.meta.requiresAuth && !token) {
    // 未登录访问受保护页面
    if (to.path.startsWith('/admin')) {
      next('/admin/login')
    } else {
      next('/login')
    }
  } else if (to.path === '/admin/login' && token) {
    // 已登录访问管理员登录页
    if (checkIsAdmin()) {
      next('/admin')
    } else {
      next('/chat')
    }
  } else if ((to.path === '/login' || to.path === '/register') && token) {
    // 已登录访问普通登录/注册页 -> 跳转聊天页
    next('/chat')
  } else if (to.meta.requiresAdmin && !checkIsAdmin()) {
    // 非管理员访问管理页 -> 跳转管理员登录
    next('/admin/login')
  } else {
    next()
  }
})

export default router