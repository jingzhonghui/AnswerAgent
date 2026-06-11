<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAdminUsers, createAdminUser, updateAdminUser, deleteAdminUser } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { AdminUserInfo } from '@/types'

const authStore = useAuthStore()
const users = ref<AdminUserInfo[]>([])
const isLoading = ref(false)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')

// 新建用户表单
const showCreateForm = ref(false)
const newUsername = ref('')
const newPassword = ref('')
const newIsAdmin = ref(false)
const isCreating = ref(false)

onMounted(async () => {
  await loadUsers()
})

async function loadUsers() {
  isLoading.value = true
  try {
    users.value = await getAdminUsers()
  } catch {
    showMessage('加载用户列表失败', 'error')
  } finally {
    isLoading.value = false
  }
}

async function handleCreate() {
  if (!newUsername.value.trim() || !newPassword.value.trim()) {
    showMessage('用户名和密码不能为空', 'error')
    return
  }
  if (newPassword.value.length < 6) {
    showMessage('密码长度至少 6 位', 'error')
    return
  }

  isCreating.value = true
  try {
    await createAdminUser({
      username: newUsername.value.trim(),
      password: newPassword.value,
      is_admin: newIsAdmin.value,
    })
    showMessage('用户创建成功', 'success')
    showCreateForm.value = false
    newUsername.value = ''
    newPassword.value = ''
    newIsAdmin.value = false
    await loadUsers()
  } catch (e: any) {
    showMessage(e?.response?.data?.detail || '创建失败', 'error')
  } finally {
    isCreating.value = false
  }
}

async function handleToggleAdmin(user: AdminUserInfo) {
  const newVal = !user.is_admin
  try {
    await updateAdminUser(user.id, { is_admin: newVal })
    user.is_admin = newVal
    showMessage(`已${newVal ? '设为' : '取消'}管理员: ${user.username}`, 'success')
  } catch (e: any) {
    showMessage(e?.response?.data?.detail || '操作失败', 'error')
  }
}

async function handleDelete(user: AdminUserInfo) {
  if (user.id === authStore.user?.id) {
    showMessage('不能删除自己', 'error')
    return
  }
  if (!confirm(`确定要删除用户 "${user.username}" 及其所有对话吗？此操作不可撤销。`)) return

  try {
    await deleteAdminUser(user.id)
    users.value = users.value.filter(u => u.id !== user.id)
    showMessage(`已删除用户: ${user.username}`, 'success')
  } catch (e: any) {
    showMessage(e?.response?.data?.detail || '删除失败', 'error')
  }
}

function showMessage(msg: string, type: 'success' | 'error') {
  message.value = msg
  messageType.value = type
  setTimeout(() => { message.value = '' }, 3000)
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>用户管理</h1>
        <p class="subtitle">共 {{ users.length }} 个用户</p>
      </div>
      <button class="btn btn-primary" @click="showCreateForm = !showCreateForm">
        {{ showCreateForm ? '取消' : '+ 新建用户' }}
      </button>
    </div>

    <div v-if="message" class="message" :class="messageType">
      {{ message }}
    </div>

    <!-- 新建用户表单 -->
    <div v-if="showCreateForm" class="create-card">
      <h3>新建用户</h3>
      <div class="form-row">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="newUsername" type="text" class="form-input" placeholder="2-50 个字符" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="newPassword" type="password" class="form-input" placeholder="至少 6 位" />
        </div>
        <div class="form-group checkbox-group">
          <label class="checkbox-label">
            <input v-model="newIsAdmin" type="checkbox" />
            <span>设为管理员</span>
          </label>
        </div>
      </div>
      <button class="btn btn-primary" :disabled="isCreating" @click="handleCreate">
        {{ isCreating ? '创建中...' : '确认创建' }}
      </button>
    </div>

    <!-- 用户列表 -->
    <div v-if="isLoading" class="loading">加载中...</div>
    <div v-else-if="users.length === 0" class="empty">暂无用户</div>
    <table v-else class="user-table">
      <thead>
        <tr>
          <th>用户名</th>
          <th>角色</th>
          <th>对话数</th>
          <th>注册时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id">
          <td class="username-cell">
            <span class="username">{{ user.username }}</span>
            <span v-if="user.id === authStore.user?.id" class="tag tag-me">我</span>
          </td>
          <td>
            <span class="tag" :class="user.is_admin ? 'tag-admin' : 'tag-user'">
              {{ user.is_admin ? '管理员' : '普通用户' }}
            </span>
          </td>
          <td>{{ user.conversation_count }}</td>
          <td class="date-cell">{{ formatDate(user.created_at) }}</td>
          <td class="actions-cell">
            <button
              class="btn-sm"
              :class="user.is_admin ? 'btn-warn' : 'btn-ok'"
              :disabled="user.id === authStore.user?.id"
              :title="user.id === authStore.user?.id ? '不能修改自己的角色' : ''"
              @click="handleToggleAdmin(user)"
            >
              {{ user.is_admin ? '取消管理员' : '设为管理员' }}
            </button>
            <button
              class="btn-sm btn-danger"
              :disabled="user.id === authStore.user?.id"
              @click="handleDelete(user)"
            >
              删除
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.page {
  max-width: 900px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
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

.btn-sm {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.btn-sm:hover:not(:disabled) {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.btn-sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-danger {
  color: #dc2626;
  border-color: #fecaca;
}

.btn-danger:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #dc2626;
  color: #dc2626;
}

[data-theme="dark"] .btn-danger {
  color: #fca5a5;
  border-color: #7f1d1d;
}

[data-theme="dark"] .btn-danger:hover:not(:disabled) {
  background: #7f1d1d;
}

.message {
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 20px;
}

.message.success {
  background: #ecfdf5;
  color: #065f46;
}

.message.error {
  background: #fef2f2;
  color: #991b1b;
}

[data-theme="dark"] .message.success {
  background: #064e3b;
  color: #a7f3d0;
}

[data-theme="dark"] .message.error {
  background: #7f1d1d;
  color: #fecaca;
}

.loading {
  color: var(--text-tertiary);
  font-size: 14px;
}

.empty {
  color: var(--text-tertiary);
  font-size: 14px;
  text-align: center;
  padding: 40px;
}

/* 创建表单 */
.create-card {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  margin-bottom: 24px;
}

.create-card h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.form-row {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 160px;
}

.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.checkbox-group {
  flex: 0 0 auto;
  min-width: auto;
  display: flex;
  align-items: flex-end;
  padding-bottom: 2px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-color);
}

/* 用户表格 */
.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.user-table th {
  text-align: left;
  padding: 10px 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.user-table td {
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.username-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  color: var(--text-primary);
  font-weight: 500;
}

.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.tag-me {
  background: var(--accent-color);
  color: #fff;
}

.tag-admin {
  background: #fef3c7;
  color: #92400e;
}

.tag-user {
  background: #f0f0f0;
  color: #666;
}

[data-theme="dark"] .tag-admin {
  background: #78350f;
  color: #fde68a;
}

[data-theme="dark"] .tag-user {
  background: #333;
  color: #999;
}

.date-cell {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.actions-cell {
  display: flex;
  gap: 6px;
}
</style>