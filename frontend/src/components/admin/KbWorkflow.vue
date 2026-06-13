<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  startWorkflow,
  startWorkflowUpload,
  getWorkflowStatus,
  pauseWorkflow,
  resumeWorkflow,
  cancelWorkflow,
  listWorkflows,
  streamWorkflowLog,
} from '@/api'
import type { WorkflowTask, WorkflowLogEntry, InputType } from '@/types'

// ============================================================
// 状态
// ============================================================

const inputType = ref<InputType>('local_path')
const inputValue = ref('')
const uploadFile = ref<File | null>(null)
const isStarting = ref(false)
const error = ref('')

const workflows = ref<WorkflowTask[]>([])
const hasRunning = ref(false)
const activeTaskId = ref<string | null>(null)
const activeTask = ref<WorkflowTask | null>(null)
const logs = ref<WorkflowLogEntry[]>([])
const logContainer = ref<HTMLElement | null>(null)
const autoScroll = ref(true)

let abortController: AbortController | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

// ============================================================
// 计算属性
// ============================================================

const statusLabel: Record<string, string> = {
  pending: '等待中',
  preprocessing: '预处理中',
  analyzing: '分析中',
  executing: '执行中',
  completed: '已完成',
  failed: '已失败',
  paused: '已暂停',
}

const statusClass: Record<string, string> = {
  pending: 'badge-gray',
  preprocessing: 'badge-blue',
  analyzing: 'badge-blue',
  executing: 'badge-blue',
  completed: 'badge-green',
  failed: 'badge-red',
  paused: 'badge-yellow',
}

const stageLabel: Record<string, string> = {
  init: '初始化',
  preprocessing: '预处理',
  analyzing: '分析',
  executing: '生成',
  completed: '完成',
}

const inputTypeLabel: Record<string, string> = {
  local_path: '本地路径',
  git_url: 'Git 地址',
  archive: '压缩包',
}

const isRunning = () => {
  if (!activeTask.value) return false
  return ['preprocessing', 'analyzing', 'executing'].includes(activeTask.value.status)
}

const isPaused = () => activeTask.value?.status === 'paused'
const isCompleted = () => activeTask.value?.status === 'completed'
const isFailed = () => activeTask.value?.status === 'failed'

const progressPercent = () => {
  if (!activeTask.value) return 0
  const tasks = activeTask.value.task_list
  if (tasks.length === 0) {
    const stages = ['init', 'preprocessing', 'analyzing', 'executing', 'completed']
    const idx = stages.indexOf(activeTask.value.stage)
    return idx >= 0 ? Math.round((idx / (stages.length - 1)) * 100) : 0
  }
  const done = activeTask.value.completed_tasks.length
  return Math.round((done / tasks.length) * 100)
}

// ============================================================
// 方法
// ============================================================

async function loadWorkflows() {
  try {
    const result = await listWorkflows()
    workflows.value = result.workflows
    hasRunning.value = result.has_running
  } catch {
    // 静默处理
  }
}

async function handleStart() {
  error.value = ''

  if (inputType.value === 'archive') {
    if (!uploadFile.value) {
      error.value = '请选择文件'
      return
    }
  } else {
    if (!inputValue.value.trim()) {
      error.value = '请输入' + (inputType.value === 'git_url' ? 'Git 地址' : '路径')
      return
    }
  }

  isStarting.value = true
  try {
    let result
    if (inputType.value === 'archive' && uploadFile.value) {
      result = await startWorkflowUpload(uploadFile.value)
    } else {
      result = await startWorkflow({ input_type: inputType.value, input_value: inputValue.value })
    }

    activeTaskId.value = result.task_id
    logs.value = []
    await loadWorkflows()
    await pollStatus()
    connectLogStream()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '启动失败'
  } finally {
    isStarting.value = false
  }
}

async function handlePause() {
  if (!activeTaskId.value) return
  try {
    await pauseWorkflow(activeTaskId.value)
    await pollStatus()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '暂停失败'
  }
}

async function handleResume() {
  if (!activeTaskId.value) return
  try {
    await resumeWorkflow(activeTaskId.value)
    logs.value = []
    connectLogStream()
    await pollStatus()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '恢复失败'
  }
}

async function handleCancel() {
  if (!activeTaskId.value) return
  try {
    await cancelWorkflow(activeTaskId.value)
    disconnectLogStream()
    await pollStatus()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '取消失败'
  }
}

async function handleDelete(taskId: string) {
  try {
    await cancelWorkflow(taskId)
    if (activeTaskId.value === taskId) {
      activeTaskId.value = null
      activeTask.value = null
      logs.value = []
      disconnectLogStream()
      stopPolling()
    }
    await loadWorkflows()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '删除失败'
  }
}

function selectWorkflow(task: WorkflowTask) {
  activeTaskId.value = task.id
  activeTask.value = task
  logs.value = []

  if (['preprocessing', 'analyzing', 'executing'].includes(task.status)) {
    connectLogStream()
    startPolling()
  } else if (['completed', 'failed', 'paused'].includes(task.status)) {
    // 已完成/失败/暂停的任务，连接 SSE 获取历史日志
    connectLogStream()
  }
}

async function pollStatus() {
  if (!activeTaskId.value) return
  try {
    const status = await getWorkflowStatus(activeTaskId.value)
    activeTask.value = status
    // 更新列表中的对应项
    const idx = workflows.value.findIndex(w => w.id === status.id)
    if (idx >= 0) {
      workflows.value[idx] = status
    }
    if (status.status === 'completed' || status.status === 'failed') {
      stopPolling()
      loadWorkflows()  // 刷新列表和运行状态
    }
  } catch {
    // 静默处理
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollStatus, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function connectLogStream() {
  disconnectLogStream()
  if (!activeTaskId.value) return

  abortController = new AbortController()
  streamWorkflowLog(
    activeTaskId.value,
    {
      onLog(entry) {
        logs.value.push(entry)
        if (autoScroll.value) {
          nextTick(() => {
            if (logContainer.value) {
              logContainer.value.scrollTop = logContainer.value.scrollHeight
            }
          })
        }
      },
      onDone() {
        pollStatus()
      },
      onError(msg) {
        logs.value.push({ timestamp: new Date().toISOString(), message: `[错误] ${msg}` })
      },
    },
    abortController.signal,
  ).catch(() => {
    // 连接断开，静默处理
  })
}

function disconnectLogStream() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
}

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    uploadFile.value = target.files[0]
  }
}

function handleLogScroll() {
  if (!logContainer.value) return
  const el = logContainer.value
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 50
}

function formatTime(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

// ============================================================
// 生命周期
// ============================================================

onMounted(() => {
  loadWorkflows()
})

onUnmounted(() => {
  disconnectLogStream()
  stopPolling()
})
</script>

<template>
  <div class="kb-workflow">
    <div class="workflow-layout">
      <!-- 左侧：工作流列表 -->
      <div class="workflow-sidebar">
        <h3 class="sidebar-title">工作流列表</h3>
        <div class="workflow-list">
          <div
            v-for="wf in workflows"
            :key="wf.id"
            class="workflow-item"
            :class="{ active: activeTaskId === wf.id }"
            @click="selectWorkflow(wf)"
          >
            <span class="wf-status" :class="statusClass[wf.status] || 'badge-gray'">
              {{ statusLabel[wf.status] || wf.status }}
            </span>
            <div class="wf-info">
              <div class="wf-type">{{ inputTypeLabel[wf.input_type] || wf.input_type }}</div>
              <div class="wf-value">{{ wf.knowledge_name || wf.input_value }}</div>
              <div class="wf-time">{{ formatTime(wf.created_at) }}</div>
            </div>
            <button
              class="wf-delete-btn"
              title="删除"
              @click.stop="handleDelete(wf.id)"
            >×</button>
          </div>
          <div v-if="workflows.length === 0" class="empty-hint">
            暂无工作流
          </div>
        </div>
      </div>

      <!-- 右侧：主内容区 -->
      <div class="workflow-main">
        <!-- 输入面板 -->
        <div class="input-panel" :class="{ disabled: hasRunning }">
          <h3 class="panel-title">新建知识库生成任务</h3>

          <div v-if="hasRunning" class="running-notice">
            当前有工作流正在执行，请等待完成后再创建新任务
          </div>

          <div class="input-type-selector">
            <label
              v-for="opt in [
                { key: 'local_path', label: '本地路径' },
                { key: 'git_url', label: 'Git 地址' },
                { key: 'archive', label: '上传压缩包' },
              ]"
              :key="opt.key"
              class="type-option"
              :class="{ active: inputType === opt.key && !hasRunning }"
            >
              <input
                type="radio"
                :value="opt.key"
                v-model="inputType"
                class="type-radio"
                :disabled="hasRunning"
              />
              {{ opt.label }}
            </label>
          </div>

          <div class="input-row">
            <input
              v-if="inputType !== 'archive'"
              v-model="inputValue"
              type="text"
              class="value-input"
              :placeholder="inputType === 'git_url' ? '输入 Git 仓库地址，如 https://github.com/...' : '输入服务器上的目录路径，如 /data/projects/...'"
              :disabled="isStarting || hasRunning"
              @keyup.enter="handleStart"
            />
            <div v-else class="file-upload-row">
              <input
                type="file"
                accept=".zip,.tar.gz,.tgz,.gz"
                class="file-input"
                @change="handleFileChange"
                :disabled="isStarting || hasRunning"
              />
              <span v-if="uploadFile" class="file-name">{{ uploadFile.name }}</span>
            </div>
            <button
              class="btn btn-start"
              :disabled="isStarting || hasRunning"
              @click="handleStart"
            >
              {{ isStarting ? '启动中...' : '开始生成' }}
            </button>
          </div>

          <div v-if="error" class="error-msg">{{ error }}</div>
        </div>

        <!-- 进度面板 -->
        <div v-if="activeTask" class="progress-panel">
          <div class="progress-header">
            <span class="task-id">任务 ID: {{ activeTask.id.substring(0, 8) }}...</span>
            <span class="wf-status" :class="statusClass[activeTask.status] || 'badge-gray'">
              {{ statusLabel[activeTask.status] || activeTask.status }}
            </span>
            <span class="stage-badge">{{ stageLabel[activeTask.stage] || activeTask.stage }}</span>
            <span v-if="activeTask.knowledge_name" class="kb-name">
              知识库: {{ activeTask.knowledge_name }}
            </span>
          </div>

          <div class="progress-bar-container">
            <div class="progress-bar" :style="{ width: progressPercent() + '%' }"></div>
            <span class="progress-text">{{ progressPercent() }}%</span>
          </div>

          <div v-if="activeTask.task_list.length > 0" class="task-summary">
            任务: {{ activeTask.completed_tasks.length }} / {{ activeTask.task_list.length }}
          </div>

          <div class="progress-actions">
            <button
              v-if="isRunning()"
              class="btn btn-pause"
              @click="handlePause"
            >
              暂停
            </button>
            <button
              v-if="isPaused() || isFailed()"
              class="btn btn-resume"
              @click="handleResume"
            >
              继续
            </button>
            <button
              v-if="isRunning() || isPaused()"
              class="btn btn-cancel"
              @click="handleCancel"
            >
              取消
            </button>
          </div>

          <div v-if="activeTask.error" class="error-msg">
            错误: {{ activeTask.error }}
          </div>
          <div v-if="isCompleted() && activeTask.result_path" class="success-msg">
            知识库已生成: {{ activeTask.result_path }}
          </div>
        </div>

        <!-- 日志查看器 -->
        <div v-if="activeTask" class="log-panel">
          <div class="log-header">
            <h3>执行日志</h3>
            <button class="btn-clear-log" @click="logs = []">清空</button>
          </div>
          <div
            ref="logContainer"
            class="log-container"
            @scroll="handleLogScroll"
          >
            <div v-if="logs.length === 0" class="log-empty">
              等待日志...
            </div>
            <div v-for="(entry, i) in logs" :key="i" class="log-line">
              <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
              <span class="log-msg">{{ entry.message }}</span>
            </div>
          </div>
        </div>

        <div v-if="!activeTask" class="empty-state">
          <p>选择一个已有工作流查看详情，或填写上方表单创建新任务</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-workflow {
  height: 100%;
}

.workflow-layout {
  display: flex;
  gap: 24px;
  height: 100%;
}

/* 左侧列表 */
.workflow-sidebar {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--border-color);
  padding-right: 16px;
  overflow-y: auto;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.workflow-item {
  position: relative;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
  border: 1px solid transparent;
}

.workflow-item:hover {
  background: var(--bg-hover);
}

.workflow-item.active {
  background: var(--bg-hover);
  border-color: var(--accent-color);
}

.wf-info {
  margin-top: 4px;
}

.wf-type {
  font-size: 11px;
  color: var(--text-tertiary);
}

.wf-value {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.wf-time {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.wf-delete-btn {
  position: absolute;
  top: 6px;
  right: 8px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 16px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
  line-height: 1;
}

.workflow-item:hover .wf-delete-btn {
  opacity: 1;
}

.wf-delete-btn:hover {
  background: #fee2e2;
  color: #dc2626;
}

[data-theme="dark"] .wf-delete-btn:hover {
  background: #7f1d1d;
  color: #fca5a5;
}

/* 右侧主区域 */
.workflow-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

/* 输入面板 */
.input-panel {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 20px;
}

.input-panel.disabled {
  opacity: 0.6;
  pointer-events: none;
}

.running-notice {
  padding: 8px 14px;
  margin-bottom: 12px;
  background: #fef3c7;
  color: #92400e;
  border-radius: var(--radius-sm);
  font-size: 13px;
  border: 1px solid #fcd34d;
}

[data-theme="dark"] .running-notice {
  background: #78350f;
  color: #fde68a;
  border-color: #a16207;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px;
}

.input-type-selector {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.type-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.type-option:hover {
  border-color: var(--accent-color);
  color: var(--text-primary);
}

.type-option.active {
  background: var(--accent-color);
  color: #fff;
  border-color: var(--accent-color);
}

.type-radio {
  display: none;
}

.input-row {
  display: flex;
  gap: 10px;
}

.value-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.value-input:focus {
  border-color: var(--accent-color);
}

.file-upload-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-input {
  font-size: 13px;
  color: var(--text-secondary);
}

.file-name {
  font-size: 12px;
  color: var(--accent-color);
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-start {
  background: var(--accent-color);
  color: #fff;
}

.btn-start:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-pause {
  background: #f59e0b;
  color: #fff;
}

.btn-pause:hover {
  background: #d97706;
}

.btn-resume {
  background: #10b981;
  color: #fff;
}

.btn-resume:hover {
  background: #059669;
}

.btn-cancel {
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.btn-cancel:hover {
  border-color: #dc2626;
  color: #dc2626;
}

/* 进度面板 */
.progress-panel {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.task-id {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.stage-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #e0e7ff;
  color: #3730a3;
}

[data-theme="dark"] .stage-badge {
  background: #312e81;
  color: #c7d2fe;
}

.kb-name {
  font-size: 12px;
  color: var(--text-secondary);
}

.progress-bar-container {
  height: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
  position: relative;
}

.progress-bar {
  height: 100%;
  background: var(--accent-color);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-text {
  position: absolute;
  right: 0;
  top: -18px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.task-summary {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.progress-actions {
  display: flex;
  gap: 8px;
}

/* 状态徽章 */
.wf-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.badge-gray { background: #e5e7eb; color: #374151; }
.badge-blue { background: #dbeafe; color: #1e40af; }
.badge-green { background: #d1fae5; color: #065f46; }
.badge-red { background: #fee2e2; color: #991b1b; }
.badge-yellow { background: #fef3c7; color: #92400e; }

[data-theme="dark"] .badge-gray { background: #374151; color: #d1d5db; }
[data-theme="dark"] .badge-blue { background: #1e3a5f; color: #93c5fd; }
[data-theme="dark"] .badge-green { background: #064e3b; color: #a7f3d0; }
[data-theme="dark"] .badge-red { background: #7f1d1d; color: #fecaca; }
[data-theme="dark"] .badge-yellow { background: #78350f; color: #fde68a; }

/* 日志面板 */
.log-panel {
  flex: 1;
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  min-height: 300px;
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #333;
}

.log-header h3 {
  font-size: 13px;
  font-weight: 600;
  color: #ccc;
  margin: 0;
}

.btn-clear-log {
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid #555;
  border-radius: 4px;
  background: transparent;
  color: #999;
  cursor: pointer;
}

.btn-clear-log:hover {
  background: #333;
  color: #ccc;
}

.log-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.7;
}

.log-empty {
  color: #666;
  font-style: italic;
}

.log-line {
  display: flex;
  gap: 12px;
}

.log-time {
  color: #888;
  white-space: nowrap;
  flex-shrink: 0;
}

.log-msg {
  color: #d4d4d4;
  word-break: break-all;
}

/* 消息 */
.error-msg {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fee2e2;
  color: #991b1b;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

[data-theme="dark"] .error-msg {
  background: #7f1d1d;
  color: #fecaca;
}

.success-msg {
  margin-top: 8px;
  padding: 8px 12px;
  background: #d1fae5;
  color: #065f46;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

[data-theme="dark"] .success-msg {
  background: #064e3b;
  color: #a7f3d0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: 14px;
}

.empty-hint {
  padding: 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>