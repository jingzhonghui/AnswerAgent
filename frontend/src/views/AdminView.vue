<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { apiChangePassword } from '@/api'
import ModelConfig from '@/components/admin/ModelConfig.vue'
import UserManagement from '@/components/admin/UserManagement.vue'
import ConversationManagement from '@/components/admin/ConversationManagement.vue'
import KbWorkflow from '@/components/admin/KbWorkflow.vue'
import KbManagement from '@/components/admin/KbManagement.vue'

const router = useRouter()
const authStore = useAuthStore()

type TabKey = 'model' | 'users' | 'conversations' | 'workflow' | 'knowledge'

function getSavedTab(): TabKey {
  const saved = localStorage.getItem('admin_active_tab')
  if (saved && ['model', 'users', 'conversations', 'workflow', 'knowledge'].includes(saved)) {
    return saved as TabKey
  }
  return 'model'
}

const activeTab = ref<TabKey>(getSavedTab())

watch(activeTab, (val) => {
  localStorage.setItem('admin_active_tab', val)
})

const tabs: { key: TabKey; label: string; icon: string }[] = [
  { key: 'model', label: '模型配置', icon: '⚙️' },
  { key: 'users', label: '用户管理', icon: '👥' },
  { key: 'conversations', label: '会话管理', icon: '💬' },
  { key: 'workflow', label: '知识库生成', icon: '📚' },
  { key: 'knowledge', label: '知识库管理', icon: '📁' },
]

// 修改密码弹窗
const showPasswordModal = ref(false)
const passwordForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordMessage = ref('')
const passwordMessageType = ref<'success' | 'error'>('success')
const isChangingPassword = ref(false)

// 用户菜单
const showMenu = ref(false)
const menuRef = ref<HTMLElement | null>(null)

function toggleMenu() {
  showMenu.value = !showMenu.value
}

function handleMenuAction(action: () => void) {
  action()
  showMenu.value = false
}

function onClickOutside(event: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    showMenu.value = false
  }
}

onMounted(() => {
  if (!authStore.isAdmin) {
    router.replace('/admin/login')
  }
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})

function backToChat() {
  router.push('/chat')
}

function handleLogout() {
  authStore.token = null
  authStore.user = null
  localStorage.removeItem('access_token')
  router.push('/admin/login')
}

function openPasswordModal() {
  passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  passwordMessage.value = ''
  showPasswordModal.value = true
}

function closePasswordModal() {
  showPasswordModal.value = false
}

async function handleChangePassword() {
  passwordMessage.value = ''
  const { oldPassword, newPassword, confirmPassword } = passwordForm.value

  if (!oldPassword || !newPassword || !confirmPassword) {
    passwordMessage.value = '请填写所有字段'
    passwordMessageType.value = 'error'
    return
  }
  if (newPassword.length < 6) {
    passwordMessage.value = '新密码长度至少 6 位'
    passwordMessageType.value = 'error'
    return
  }
  if (newPassword !== confirmPassword) {
    passwordMessage.value = '两次输入的新密码不一致'
    passwordMessageType.value = 'error'
    return
  }

  isChangingPassword.value = true
  try {
    await apiChangePassword({ old_password: oldPassword, new_password: newPassword })
    showPasswordModal.value = false
  } catch (e: any) {
    passwordMessage.value = e?.response?.data?.detail || '密码修改失败'
    passwordMessageType.value = 'error'
  } finally {
    isChangingPassword.value = false
  }
}
</script>

<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="admin-sidebar">
      <div class="admin-header">
        <h2>管理后台</h2>
        <span class="admin-badge">Admin</span>
      </div>

      <nav class="admin-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="nav-icon">{{ tab.icon }}</span>
          <span class="nav-label">{{ tab.label }}</span>
        </button>
      </nav>

      <div class="admin-footer">
        <div class="user-info">
          <div class="user-avatar">{{ authStore.user?.username?.charAt(0).toUpperCase() || 'A' }}</div>
          <span class="user-name">{{ authStore.user?.username || 'Admin' }}</span>
        </div>
        <div class="user-menu-wrapper" ref="menuRef">
          <button class="menu-trigger" @click.stop="toggleMenu" title="更多">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <circle cx="5" cy="12" r="2"/>
              <circle cx="12" cy="12" r="2"/>
              <circle cx="19" cy="12" r="2"/>
            </svg>
          </button>
          <Transition name="menu-dropdown">
            <div v-if="showMenu" class="dropdown-menu">
              <button class="menu-item" @click="handleMenuAction(openPasswordModal)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
                <span>修改密码</span>
              </button>
              <button class="menu-item" @click="handleMenuAction(backToChat)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
                <span>返回聊天</span>
              </button>
              <button class="menu-item logout-item" @click="handleMenuAction(handleLogout)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
                  <polyline points="16 17 21 12 16 7"/>
                  <line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
                <span>退出登录</span>
              </button>
            </div>
          </Transition>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="admin-main">
      <ModelConfig v-if="activeTab === 'model'" />
      <UserManagement v-else-if="activeTab === 'users'" />
      <ConversationManagement v-else-if="activeTab === 'conversations'" />
      <KbWorkflow v-else-if="activeTab === 'workflow'" />
      <KbManagement v-else-if="activeTab === 'knowledge'" />
    </main>
  </div>

  <!-- 修改密码弹窗 -->
  <div v-if="showPasswordModal" class="modal-overlay" @click.self="closePasswordModal">
    <div class="modal-card">
      <div class="modal-header">
        <h3>修改密码</h3>
        <button class="modal-close" @click="closePasswordModal">✕</button>
      </div>
      <div class="modal-body">
        <div v-if="passwordMessage" class="message" :class="passwordMessageType">
          {{ passwordMessage }}
        </div>
        <div class="form-group">
          <label for="old-password">旧密码</label>
          <input
            id="old-password"
            v-model="passwordForm.oldPassword"
            type="password"
            class="form-input"
            placeholder="请输入旧密码"
            :disabled="isChangingPassword"
          />
        </div>
        <div class="form-group">
          <label for="new-password">新密码</label>
          <input
            id="new-password"
            v-model="passwordForm.newPassword"
            type="password"
            class="form-input"
            placeholder="至少 6 位"
            :disabled="isChangingPassword"
          />
        </div>
        <div class="form-group">
          <label for="confirm-password">确认新密码</label>
          <input
            id="confirm-password"
            v-model="passwordForm.confirmPassword"
            type="password"
            class="form-input"
            placeholder="再次输入新密码"
            :disabled="isChangingPassword"
          />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-cancel" @click="closePasswordModal" :disabled="isChangingPassword">
          取消
        </button>
        <button class="btn btn-primary" @click="handleChangePassword" :disabled="isChangingPassword">
          {{ isChangingPassword ? '修改中...' : '确认修改' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
}

.admin-sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  padding: 0;
}

.admin-header {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.admin-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #fef3c7;
  color: #92400e;
  font-weight: 600;
}

[data-theme="dark"] .admin-badge {
  background: #78350f;
  color: #fde68a;
}

.admin-nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-color);
  color: #ffffff;
}

.nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.admin-footer {
  padding: 12px 12px;
  border-top: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.2s;
}

.user-info:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-color);
  color: white;
  border-radius: var(--radius-full);
  font-size: 14px;
  font-weight: 500;
  flex-shrink: 0;
}

.user-name {
  font-size: 15px;
  color: var(--text-primary);
}

.user-menu-wrapper {
  position: relative;
}

.menu-trigger {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 0.15s;
}

.menu-trigger:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.menu-trigger svg {
  width: 16px;
  height: 16px;
}

.dropdown-menu {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 4px;
  min-width: 150px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  z-index: 100;
}

.menu-item {
  width: 100%;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.menu-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.menu-item svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.logout-item:hover {
  background: #fef2f2;
  color: #dc2626;
}

[data-theme="dark"] .logout-item:hover {
  background: #7f1d1d;
  color: #fca5a5;
}

.menu-dropdown-enter-active,
.menu-dropdown-leave-active {
  transition: all 0.15s ease;
}

.menu-dropdown-enter-from,
.menu-dropdown-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.admin-main {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

/* 修改密码弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 420px;
  box-shadow: var(--shadow-lg);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}

.modal-header h3 {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  font-size: 16px;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-body .message {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin: 0;
}

.modal-body .message.success {
  background: #ecfdf5;
  color: #065f46;
}

.modal-body .message.error {
  background: #fef2f2;
  color: #991b1b;
}

[data-theme="dark"] .modal-body .message.success {
  background: #064e3b;
  color: #a7f3d0;
}

[data-theme="dark"] .modal-body .message.error {
  background: #7f1d1d;
  color: #fecaca;
}

.modal-body .form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-body .form-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.modal-body .form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  transition: border-color 0.15s;
}

.modal-body .form-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 24px 20px;
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-color);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-cancel {
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.btn-cancel:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}
</style>