<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
const activeTab = ref<TabKey>('model')

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

onMounted(() => {
  if (!authStore.isAdmin) {
    router.replace('/admin/login')
  }
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
        <button class="footer-btn password-btn" @click="openPasswordModal">
          🔑 修改密码
        </button>
        <button class="footer-btn back-btn" @click="backToChat">
          ← 返回聊天
        </button>
        <button class="footer-btn logout-btn" @click="handleLogout">
          🚪 退出登录
        </button>
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
  padding: 12px 8px;
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.footer-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.footer-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent-color);
}

.password-btn:hover {
  background: var(--bg-hover);
  color: var(--accent-color);
  border-color: var(--accent-color);
}

.logout-btn:hover {
  background: #fef2f2;
  color: #dc2626;
  border-color: #dc2626;
}

[data-theme="dark"] .logout-btn:hover {
  background: #7f1d1d;
  color: #fca5a5;
  border-color: #fca5a5;
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