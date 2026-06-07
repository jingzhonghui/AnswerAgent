<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

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
    if (conv.isPinned) groupName = '置顶'
    else if (diffDays === 0) groupName = '今天'
    else if (diffDays === 1) groupName = '昨天'
    else if (diffDays < 7) groupName = '7天内'
    else if (diffDays < 30) groupName = '30天内'
    else groupName = '更早'

    if (!groups[groupName]) groups[groupName] = []
    groups[groupName].push(conv)
  })

  // 排序
  const order = ['置顶', '今天', '昨天', '7天内', '30天内', '更早']
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
</script>

<template>
  <aside class="sidebar">
    <!-- Logo -->
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon">◆</span>
        <span class="logo-text">Answer Agent</span>
      </div>
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
        <div class="user-avatar">U</div>
        <span class="user-name">用户</span>
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
}

.sidebar-header {
  padding: 16px 20px;
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
</style>
