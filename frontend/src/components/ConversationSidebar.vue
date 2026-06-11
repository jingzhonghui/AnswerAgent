<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { exportConversation } from '@/api'

const router = useRouter()
const chatStore = useChatStore()
const authStore = useAuthStore()

// 向父组件发出收起事件
const emit = defineEmits<{
  (e: 'collapse'): void
  (e: 'toggleTheme'): void
}>()

defineProps<{
  isDark: boolean
}>()

// 用户菜单状态
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
  setTimeout(() => {
    document.addEventListener('click', onClickOutside)
  }, 0)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})

const editingId = ref<string | null>(null)
const editingTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)
const hoveredId = ref<string | null>(null)

// 按时间分组对话
const groupedConversations = computed(() => {
  const groups: Record<string, typeof chatStore.conversations> = {}

  chatStore.conversations.forEach(conv => {
    const date = new Date(conv.updated_at)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

    let groupName: string
    if (diffDays === 0) groupName = '今天'
    else if (diffDays === 1) groupName = '昨天'
    else if (diffDays < 7) groupName = '7天内'
    else if (diffDays < 30) groupName = '30天内'
    else groupName = '更早'

    if (!groups[groupName]) groups[groupName] = []
    groups[groupName].push(conv)
  })

  // 排序
  const order = ['今天', '昨天', '7天内', '30天内', '更早']
  const sortedGroups: Record<string, typeof chatStore.conversations> = {}
  order.forEach(name => {
    if (groups[name] && groups[name].length > 0) {
      sortedGroups[name] = groups[name]
    }
  })

  return sortedGroups
})

onMounted(async () => {
  await chatStore.loadConversations()
  // 页面刷新后自动恢复上次打开的对话
  await chatStore.restoreSession()
})

async function handleCreateConversation() {
  await chatStore.createConversation()
}

async function handleSelectConversation(id: string) {
  if (editingId.value) return
  await chatStore.selectConversation(id)
}

function startRename(event: Event, id: string, title: string) {
  event.stopPropagation()
  editingId.value = id
  editingTitle.value = title
  nextTick(() => {
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}

async function finishEditing() {
  if (editingId.value && editingTitle.value.trim()) {
    const trimmedTitle = editingTitle.value.trim()
    if (trimmedTitle !== chatStore.conversations.find(c => c.id === editingId.value)?.title) {
      await chatStore.renameConversation(editingId.value, trimmedTitle)
    }
  }
  editingId.value = null
  editingTitle.value = ''
}

function cancelEditing() {
  editingId.value = null
  editingTitle.value = ''
}

function handleEditKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') finishEditing()
  else if (event.key === 'Escape') cancelEditing()
}

async function handleDelete(event: Event, id: string) {
  event.stopPropagation()
  if (confirm('确定要删除这个对话吗？')) {
    await chatStore.deleteConversation(id)
  }
}

async function handleExport(event: Event, id: string, title: string) {
  event.stopPropagation()
  // 生成安全的文件名
  const safeTitle = title.replace(/[/\\:*?"<>|]/g, '_')
  await exportConversation(id, `${safeTitle}.md`)
}
</script>

<template>
  <aside class="sidebar">
    <!-- Logo -->
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon">
          <svg viewBox="0 0 1024 1024" width="16" height="16" fill="currentColor">
            <path d="M231.936 409.6v174.592H161.792V409.6h70.144m0-34.816H161.792c-19.456 0-34.816 15.872-34.816 34.816v174.592c0 18.944 15.872 34.816 34.816 34.816h69.632c19.456 0 34.816-15.872 34.816-34.816V409.6c0.512-18.944-15.36-34.816-34.304-34.816zM860.16 409.6v174.592h-69.632V409.6H860.16m0-34.816h-69.632c-18.944 0-34.816 15.872-34.816 34.816v174.592c0 19.456 15.872 34.816 34.816 34.816H860.16c19.456 0 34.816-15.872 34.816-34.816V409.6c0-18.944-15.36-34.816-34.816-34.816z m-349.184 349.184c38.4 0 69.632 31.232 69.632 69.632s-31.232 69.632-69.632 69.632-69.632-31.232-69.632-69.632 31.232-69.632 69.632-69.632m0-34.816c-57.856 0-104.448 47.104-104.448 104.448 0 57.856 47.104 104.96 104.448 104.96s104.448-47.104 104.448-104.448-46.592-104.96-104.448-104.96zM441.344 374.784H371.2v69.632h69.632V374.784z m209.408 0h-69.632v69.632h69.632V374.784z m-19.456 174.592c-24.064 41.472-68.608 69.632-120.32 69.632s-96.256-28.16-120.32-69.632h-39.424c27.136 61.44 88.064 104.448 159.744 104.448s132.608-43.008 159.744-104.448h-39.424z"/>
            <path d="M215.04 374.784c43.52-121.856 159.232-209.408 295.936-209.408s252.416 87.552 295.936 209.408h37.376c-44.544-141.824-176.64-244.224-333.312-244.224s-288.256 102.912-332.8 244.224H215.04z m577.024 244.224c-36.352 72.704-99.328 129.024-176.128 156.16v37.376c96.768-30.208 175.104-101.376 215.04-193.536h-38.912z"/>
          </svg>
        </span>
        <span class="logo-text">Answer Agent</span>
      </div>
      <button
        class="collapse-btn"
        @click="emit('collapse')"
        title="收起侧边栏"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="4" width="18" height="16" rx="2"/>
          <path d="M9 4v16"/>
          <path d="M16 10l-3 2 3 2"/>
        </svg>
      </button>
    </div>

    <!-- 新建对话按钮 -->
    <div class="sidebar-actions">
      <button class="new-chat-btn" @click="handleCreateConversation">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 8v8M8 12h8"/>
        </svg>
        <span>开启新对话</span>
      </button>
    </div>

    <!-- 对话列表 -->
    <div class="conversation-list">
      <div v-if="chatStore.conversations.length === 0" class="empty-state">
        暂无对话
      </div>

      <template v-else>
        <div
          v-for="(convs, groupName) in groupedConversations"
          :key="groupName"
          class="conversation-group"
        >
          <div class="group-label">{{ groupName }}</div>
          <div
            v-for="conv in convs"
            :key="conv.id"
            class="conversation-item"
            :class="{ active: conv.id === chatStore.activeConversationId }"
            @click="handleSelectConversation(conv.id)"
            @mouseenter="hoveredId = conv.id"
            @mouseleave="hoveredId = null"
          >
            <template v-if="editingId === conv.id">
              <input
                ref="editInputRef"
                v-model="editingTitle"
                class="edit-input"
                @blur="finishEditing"
                @keydown="handleEditKeydown"
                @click.stop
              />
            </template>
            <template v-else>
              <span class="conversation-title">{{ conv.title }}</span>
              <div
                v-if="hoveredId === conv.id || conv.id === chatStore.activeConversationId"
                class="conversation-actions"
                @click.stop
              >
                <button
                  class="action-btn"
                  @click="handleExport($event, conv.id, conv.title)"
                  title="导出为 Markdown"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                </button>
                <button
                  class="action-btn"
                  @click="startRename($event, conv.id, conv.title)"
                  title="重命名"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
                <button
                  class="action-btn delete"
                  @click="handleDelete($event, conv.id)"
                  title="删除"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                  </svg>
                </button>
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部用户信息 -->
    <div class="sidebar-footer">
      <div class="user-info">
        <div class="user-avatar">{{ authStore.user?.username?.charAt(0).toUpperCase() || 'U' }}</div>
        <span class="user-name">{{ authStore.user?.username || '用户' }}</span>
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
            <button class="menu-item" @click="handleMenuAction(() => emit('toggleTheme'))">
              <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
              </svg>
              <span>{{ isDark ? '亮色主题' : '暗色主题' }}</span>
            </button>
            <button class="menu-item logout-item" @click="handleMenuAction(() => authStore.logout())">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              <span>退出登录</span>
            </button>
            <button
              v-if="authStore.isAdmin"
              class="menu-item admin-item"
              @click="handleMenuAction(() => router.push('/admin'))"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
              </svg>
              <span>管理后台</span>
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  white-space: nowrap;
}

.sidebar-header {
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.collapse-btn {
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
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.collapse-btn svg {
  width: 18px;
  height: 18px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.logo-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-color);
  color: white;
  border-radius: var(--radius-sm);
  font-size: 14px;
}

.sidebar-actions {
  padding: 0 16px 16px;
}

.new-chat-btn {
  width: 100%;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.new-chat-btn svg {
  width: 16px;
  height: 16px;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px;
}

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.conversation-group {
  margin-bottom: 16px;
}

.group-label {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 14px;
  transition: all 0.15s;
  position: relative;
}

.conversation-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.conversation-item.active {
  background: var(--bg-active);
  color: var(--text-primary);
}

.conversation-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 8px;
}

.edit-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--accent-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.conversation-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.action-btn {
  width: 24px;
  height: 24px;
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

.action-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.action-btn.delete:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.action-btn svg {
  width: 14px;
  height: 14px;
}

.sidebar-footer {
  padding: 12px 16px;
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
}

.user-name {
  font-size: 14px;
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
  font-size: 13px;
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

.menu-item.logout-item:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.menu-item.admin-item {
  border-top: 1px solid var(--border-color);
}

.menu-item.admin-item:hover {
  background: rgba(78, 110, 242, 0.1);
  color: var(--accent-color);
}

.menu-dropdown-enter-active,
.menu-dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.menu-dropdown-enter-from,
.menu-dropdown-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
