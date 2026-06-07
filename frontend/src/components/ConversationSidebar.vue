<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

// 重命名相关状态
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

// 确认删除相关状态
const showDeleteConfirm = ref(false)
const deleteTargetId = ref<string | null>(null)

// 右键菜单相关状态
const showContextMenu = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const contextMenuTargetId = ref<string | null>(null)

// 加载对话列表
onMounted(async () => {
  await chatStore.loadConversations()
})

// 新建对话
async function handleCreateConversation() {
  await chatStore.createConversation()
}

// 选择对话
async function handleSelectConversation(id: string) {
  // 如果正在编辑，先结束编辑
  if (editingId.value) {
    finishEditing()
  }
  await chatStore.selectConversation(id)
}

// 开始重命名
function startRename(event: Event, id: string, title: string) {
  event.stopPropagation()
  editingId.value = id
  editingTitle.value = title
  // 关闭右键菜单
  hideContextMenu()
  // 等待 DOM 更新后聚焦输入框
  nextTick(() => {
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}

// 结束重命名
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

// 取消编辑
function cancelEditing() {
  editingId.value = null
  editingTitle.value = ''
}

// 处理输入框键盘事件
function handleEditKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    finishEditing()
  } else if (event.key === 'Escape') {
    cancelEditing()
  }
}

// 确认删除
function confirmDelete(id: string) {
  deleteTargetId.value = id
  showDeleteConfirm.value = true
  hideContextMenu()
}

// 执行删除
async function executeDelete() {
  if (deleteTargetId.value) {
    await chatStore.deleteConversation(deleteTargetId.value)
  }
  showDeleteConfirm.value = false
  deleteTargetId.value = null
}

// 取消删除
function cancelDelete() {
  showDeleteConfirm.value = false
  deleteTargetId.value = null
}

// 显示右键菜单
function showContextMenuForItem(event: MouseEvent, id: string) {
  event.preventDefault()
  contextMenuTargetId.value = id
  contextMenuX.value = event.clientX
  contextMenuY.value = event.clientY
  showContextMenu.value = true
}

// 隐藏右键菜单
function hideContextMenu() {
  showContextMenu.value = false
  contextMenuTargetId.value = null
}

// 点击其他地方隐藏菜单
function handleDocumentClick() {
  hideContextMenu()
}

// 获取对话标题
function getConversationTitle(id: string): string {
  const conv = chatStore.conversations.find(c => c.id === id)
  return conv?.title || ''
}
</script>

<template>
  <aside class="sidebar" @click="hideContextMenu">
    <!-- 头部 -->
    <div class="sidebar-header">
      <h1 class="logo">Answer Agent</h1>
    </div>

    <!-- 新建对话按钮 -->
    <div class="sidebar-actions">
      <button class="new-chat-btn" @click="handleCreateConversation">
        <span class="plus-icon">+</span>
        <span>新建对话</span>
      </button>
    </div>

    <!-- 对话列表 -->
    <div class="conversation-list" @click="handleDocumentClick">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.id"
        class="conversation-item"
        :class="{ active: conv.id === chatStore.activeConversationId }"
        @click="handleSelectConversation(conv.id)"
        @contextmenu="showContextMenuForItem($event, conv.id)"
      >
        <!-- 编辑模式 -->
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
        <!-- 显示模式 -->
        <template v-else>
          <span class="conversation-title">{{ conv.title }}</span>
          <button
            class="delete-btn"
            @click.stop="confirmDelete(conv.id)"
            title="删除对话"
          >
            ×
          </button>
        </template>
      </div>

      <!-- 空状态 -->
      <div v-if="chatStore.conversations.length === 0" class="empty-state">
        暂无对话，点击上方按钮新建
      </div>

      <!-- 加载中 -->
      <div v-if="chatStore.isLoading" class="loading-state">
        加载中...
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="showContextMenu"
      class="context-menu"
      :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px' }"
      @click.stop
    >
      <div
        class="context-menu-item"
        @click="startRename($event, contextMenuTargetId!, getConversationTitle(contextMenuTargetId!))"
      >
        重命名
      </div>
      <div
        class="context-menu-item delete"
        @click="confirmDelete(contextMenuTargetId!)"
      >
        删除
      </div>
    </div>

    <!-- 删除确认对话框 -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click="cancelDelete">
      <div class="modal-content" @click.stop>
        <h3>确认删除</h3>
        <p>确定要删除这个对话吗？此操作无法撤销。</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="cancelDelete">取消</button>
          <button class="btn-confirm" @click="executeDelete">删除</button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  position: relative;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.logo {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.sidebar-actions {
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
}

.new-chat-btn {
  width: 100%;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: var(--hover-bg);
  border-color: var(--accent-color);
}

.plus-icon {
  font-size: 16px;
  font-weight: 500;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 14px;
  transition: background 0.2s;
}

.conversation-item:hover {
  background: var(--hover-bg);
}

.conversation-item:hover .delete-btn {
  opacity: 1;
}

.conversation-item.active {
  background: var(--accent-color);
  color: white;
}

.conversation-item.active .delete-btn {
  color: white;
  opacity: 0.7;
}

.conversation-item.active .delete-btn:hover {
  opacity: 1;
}

.conversation-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.edit-input {
  flex: 1;
  padding: 4px 6px;
  border: 1px solid var(--accent-color);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.delete-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
  border-radius: 4px;
}

.delete-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.empty-state,
.loading-state {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

/* 右键菜单 */
.context-menu {
  position: fixed;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  min-width: 120px;
  overflow: hidden;
}

.context-menu-item {
  padding: 10px 16px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.2s;
}

.context-menu-item:hover {
  background: var(--hover-bg);
}

.context-menu-item.delete {
  color: #e74c3c;
}

.context-menu-item.delete:hover {
  background: rgba(231, 76, 60, 0.1);
}

/* 删除确认对话框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
  min-width: 300px;
  max-width: 90vw;
}

.modal-content h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.modal-content p {
  margin: 0 0 20px 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-cancel,
.btn-confirm {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.btn-cancel:hover {
  background: var(--hover-bg);
}

.btn-confirm {
  background: #e74c3c;
  border: 1px solid #e74c3c;
  color: white;
}

.btn-confirm:hover {
  background: #c0392b;
  border-color: #c0392b;
}
</style>
