<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  getKbList,
  getKbFiles,
  createKnowledgeBase,
  uploadKbZip,
  deleteKnowledgeBase,
  uploadKbFile,
  deleteKbFile,
  downloadKbFile,
  downloadKnowledgeBase,
  getKbFileContent,
} from '@/api'
import type { KbSummary, KbFileInfo } from '@/types'
import type { KbFileContent } from '@/api'

import hljs from 'highlight.js'
import MarkdownIt from 'markdown-it'

function _highlightCode(str: string, lang: string): string {
  if (lang && hljs.getLanguage(lang)) {
    try {
      return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
    } catch { /* fall through */ }
  }
  const escaped = str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return `<pre class="hljs"><code>${escaped}</code></pre>`
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  highlight: _highlightCode,
})

// ============================================================
// Toast 消息
// ============================================================

interface Toast {
  id: number
  type: 'success' | 'error'
  message: string
}

let toastId = 0
const toasts = ref<Toast[]>([])

function showToast(type: 'success' | 'error', message: string) {
  const id = ++toastId
  toasts.value.push({ id, type, message })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 3000)
}

// ============================================================
// 状态
// ============================================================

const knowledgeBases = ref<KbSummary[]>([])
const selectedKb = ref<string | null>(null)
const currentPath = ref('')
const kbItems = ref<KbFileInfo[]>([])
const isLoadingFiles = ref(false)

// 弹窗
const showCreateModal = ref(false)
const showUploadZipModal = ref(false)
const showUploadFileModal = ref(false)
const showDeleteKbConfirm = ref<string | null>(null)
const showDeleteConfirm = ref<{ relPath: string; name: string; isDir: boolean } | null>(null)

// 表单
const newKbName = ref('')
const uploadZipFile = ref<File | null>(null)
const uploadZipName = ref('')
const uploadKbFileTarget = ref<File | null>(null)

// 上传进度
const uploadZipProgress = ref(0)
const isUploadingZip = ref(false)

// 文件内容查看
const viewingFile = ref<KbFileInfo | null>(null)
const fileContent = ref<KbFileContent | null>(null)
const isFileContentLoading = ref(false)
const isFullscreen = ref(false)

const _EXT_LANG_MAP: Record<string, string> = {
  '.js': 'javascript', '.ts': 'typescript', '.vue': 'vue', '.jsx': 'jsx', '.tsx': 'tsx',
  '.py': 'python', '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp',
  '.cs': 'csharp', '.go': 'go', '.rs': 'rust', '.rb': 'ruby', '.php': 'php',
  '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
  '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.ps1': 'powershell',
  '.yml': 'yaml', '.yaml': 'yaml', '.json': 'json', '.xml': 'xml', '.toml': 'toml',
  '.html': 'html', '.css': 'css', '.scss': 'scss', '.less': 'less',
  '.sql': 'sql', '.graphql': 'graphql',
  '.ini': 'ini', '.cfg': 'ini', '.dockerfile': 'dockerfile',
  '.md': 'markdown',
}

/** 文件预览渲染方式：'markdown' | 'highlight' | 'plain' */
const previewRenderMode = computed(() => {
  if (!viewingFile.value) return 'plain'
  const ext = viewingFile.value.extension.toLowerCase()
  if (ext === '.md') return 'markdown'
  if (ext in _EXT_LANG_MAP) return 'highlight'
  return 'plain'
})

/** markdown 渲染后的 HTML */
const markdownHtml = computed(() => {
  if (previewRenderMode.value !== 'markdown' || !fileContent.value?.content) return ''
  return md.render(fileContent.value.content)
})

/** highlight.js 高亮后的 HTML */
const highlightHtml = computed(() => {
  if (previewRenderMode.value !== 'highlight' || !fileContent.value?.content || !viewingFile.value) return ''
  const lang = _EXT_LANG_MAP[viewingFile.value.extension.toLowerCase()] || ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      return hljs.highlight(fileContent.value.content, { language: lang, ignoreIllegals: true }).value
    } catch { /* fall through */ }
  }
  return ''
})

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function closeFileViewer() {
  viewingFile.value = null
  fileContent.value = null
  isFullscreen.value = false
}

// ============================================================
// 面包屑
// ============================================================

const breadcrumbs = computed(() => {
  if (!currentPath.value) return []
  const parts = currentPath.value.split('/')
  return parts.map((part, index) => ({
    name: part,
    path: parts.slice(0, index + 1).join('/'),
  }))
})

// ============================================================
// 方法
// ============================================================

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString()
}

async function loadList() {
  try {
    const res = await getKbList()
    knowledgeBases.value = res.knowledge_bases
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '加载知识库列表失败')
  }
}

async function selectKb(name: string) {
  selectedKb.value = name
  currentPath.value = ''
  kbItems.value = []
  await loadDir('')
}

async function loadDir(subPath: string) {
  if (!selectedKb.value) return
  isLoadingFiles.value = true
  try {
    const res = await getKbFiles(selectedKb.value, subPath || undefined)
    kbItems.value = res.items
    currentPath.value = res.current_path
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '加载文件列表失败')
  } finally {
    isLoadingFiles.value = false
  }
}

/** 双击进入目录 */
function enterDir(item: KbFileInfo) {
  if (!item.is_dir) return
  loadDir(item.rel_path)
}

/** 返回根目录 */
function goToRoot() {
  loadDir('')
}

function goToBreadcrumb(subPath: string) {
  loadDir(subPath)
}

async function handleCreate() {
  if (!newKbName.value.trim()) {
    showToast('error', '请输入知识库名称')
    return
  }
  try {
    await createKnowledgeBase({ name: newKbName.value.trim() })
    showToast('success', `知识库 "${newKbName.value.trim()}" 已创建`)
    showCreateModal.value = false
    newKbName.value = ''
    await loadList()
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '创建失败')
  }
}

async function handleUploadZip() {
  if (!uploadZipFile.value) {
    showToast('error', '请选择 ZIP 文件')
    return
  }
  isUploadingZip.value = true
  uploadZipProgress.value = 0
  try {
    const res = await uploadKbZip(
      uploadZipFile.value,
      uploadZipName.value.trim() || undefined,
      (pct) => { uploadZipProgress.value = pct },
    )
    showToast('success', `知识库 "${res.name}" 已从 ZIP 创建（${res.file_count} 个文件）`)
    showUploadZipModal.value = false
    uploadZipFile.value = null
    uploadZipName.value = ''
    uploadZipProgress.value = 0
    await loadList()
    selectedKb.value = res.name
    currentPath.value = ''
    await loadDir('')
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '上传 ZIP 失败')
  } finally {
    isUploadingZip.value = false
  }
}

async function handleDeleteKb(name: string) {
  try {
    await deleteKnowledgeBase(name)
    showToast('success', `知识库 "${name}" 已删除`)
    showDeleteKbConfirm.value = null
    if (selectedKb.value === name) {
      selectedKb.value = null
      currentPath.value = ''
      kbItems.value = []
    }
    await loadList()
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '删除失败')
  }
}

async function handleUploadFile() {
  if (!uploadKbFileTarget.value || !selectedKb.value) {
    showToast('error', '请选择文件')
    return
  }
  try {
    const res = await uploadKbFile(
      selectedKb.value,
      uploadKbFileTarget.value,
      currentPath.value || undefined,
    )
    showToast('success', `文件 "${res.file_name}" 已上传`)
    showUploadFileModal.value = false
    uploadKbFileTarget.value = null
    await loadDir(currentPath.value)
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '上传文件失败')
  }
}

async function handleDeleteItem(item: KbFileInfo) {
  if (!selectedKb.value) return
  try {
    await deleteKbFile(selectedKb.value, item.rel_path)
    showToast('success', `${item.is_dir ? '目录' : '文件'} "${item.name}" 已删除`)
    showDeleteConfirm.value = null
    await loadDir(currentPath.value)
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '删除失败')
  }
}

async function handleViewFile(item: KbFileInfo) {
  if (!selectedKb.value || item.is_dir) return
  viewingFile.value = item
  fileContent.value = null
  isFileContentLoading.value = true
  try {
    fileContent.value = await getKbFileContent(selectedKb.value, item.rel_path)
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '读取文件内容失败')
    viewingFile.value = null
  } finally {
    isFileContentLoading.value = false
  }
}

async function handleDownloadFile(item: KbFileInfo) {
  if (!selectedKb.value || item.is_dir) return
  try {
    await downloadKbFile(selectedKb.value, item.rel_path)
    showToast('success', `文件 "${item.name}" 下载中…`)
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '下载失败')
  }
}

async function handleDownloadKb(name: string) {
  try {
    await downloadKnowledgeBase(name)
    showToast('success', `知识库 "${name}" 下载中…`)
  } catch (e: any) {
    showToast('error', e?.response?.data?.detail || '下载失败')
  }
}

function onZipFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadZipFile.value = input.files?.[0] || null
}

function onKbFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadKbFileTarget.value = input.files?.[0] || null
}

// ============================================================
// 初始化
// ============================================================

onMounted(() => {
  loadList()
})
</script>

<template>
  <div class="kb-management">
    <div class="kb-layout">
      <!-- 左侧：知识库列表 -->
      <aside class="kb-sidebar">
        <h3 class="kb-sidebar-title">知识库列表</h3>

        <div class="kb-list">
          <div v-if="knowledgeBases.length === 0" class="kb-empty">
            暂无知识库
          </div>
          <button
            v-for="kb in knowledgeBases"
            :key="kb.name"
            class="kb-item"
            :class="{ active: selectedKb === kb.name }"
            @click="selectKb(kb.name)"
          >
            <div class="kb-item-header">
              <span class="kb-item-name">📁 {{ kb.name }}</span>
              <div class="kb-item-actions">
                <button
                  class="kb-item-action-btn"
                  title="下载知识库"
                  @click.stop="handleDownloadKb(kb.name)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </button>
                <button
                  class="kb-item-action-btn kb-item-delete"
                  title="删除知识库"
                  @click.stop="showDeleteKbConfirm = kb.name"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6" />
                    <path d="M14 11v6" />
                    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                  </svg>
                </button>
              </div>
            </div>
            <div class="kb-item-meta">
              <span>{{ kb.file_count }} 个文件</span>
              <span v-if="kb.last_modified" class="kb-item-time">
                {{ formatTime(kb.last_modified) }}
              </span>
            </div>
          </button>
        </div>

        <div class="kb-sidebar-actions">
          <button class="btn btn-primary" @click="showCreateModal = true">
            🎲 新建知识库
          </button>
          <button class="btn btn-accent" @click="showUploadZipModal = true">
            📦 上传压缩包
          </button>
        </div>
      </aside>

      <!-- 右侧：文件浏览器 -->
      <main class="kb-main">
        <!-- 未选中知识库 -->
        <div v-if="!selectedKb" class="kb-placeholder">
          <div class="kb-placeholder-icon">📂</div>
          <p>选择一个知识库查看文件</p>
        </div>

        <!-- 文件浏览器 -->
        <template v-else>
          <div class="kb-main-header">
            <h3>📁 {{ selectedKb }}</h3>
            <button class="btn btn-accent" @click="showUploadFileModal = true">
              ⬆️ 上传文档
            </button>
          </div>

          <!-- 面包屑导航 -->
          <div class="breadcrumb-bar">
            <button class="breadcrumb-link" @click="goToRoot()">📁 {{ selectedKb }}</button>
            <template v-for="(crumb, idx) in breadcrumbs" :key="crumb.path">
              <span class="breadcrumb-sep">/</span>
              <button
                v-if="idx < breadcrumbs.length - 1"
                class="breadcrumb-link"
                @click="goToBreadcrumb(crumb.path)"
              >
                {{ crumb.name }}
              </button>
              <span v-else class="breadcrumb-current">{{ crumb.name }}</span>
            </template>
          </div>

          <!-- 加载中 -->
          <div v-if="isLoadingFiles" class="kb-loading">加载中…</div>

          <!-- 空目录 -->
          <div v-else-if="kbItems.length === 0" class="kb-placeholder">
            <div class="kb-placeholder-icon">📭</div>
            <p>当前目录为空</p>
          </div>

          <!-- 文件/目录表格 -->
          <table v-else class="kb-file-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>大小</th>
                <th>修改时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in kbItems"
                :key="item.rel_path"
                :class="{ 'row-dir': item.is_dir }"
                @dblclick="enterDir(item)"
              >
                <td class="item-name">
                  <div class="item-name-inner">
                    <span class="item-icon">{{ item.is_dir ? '📁' : '📄' }}</span>
                    <span class="item-name-text">{{ item.name }}</span>
                  </div>
                </td>
                <td class="item-size">
                  {{ item.is_dir ? '-' : formatSize(item.size) }}
                </td>
                <td class="item-time">{{ formatTime(item.modified) }}</td>
                <td class="item-action">
                  <div class="action-group">
                    <button
                      v-if="!item.is_dir"
                      class="btn-view"
                      title="查看文件内容"
                      @click="handleViewFile(item)"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </button>
                    <button
                      v-if="!item.is_dir"
                      class="btn-download"
                      title="下载文件"
                      @click="handleDownloadFile(item)"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                    </button>
                    <button
                      class="btn-delete"
                      :title="`删除${item.is_dir ? '目录' : '文件'}`"
                      @click="showDeleteConfirm = {
                        relPath: item.rel_path,
                        name: item.name,
                        isDir: item.is_dir,
                      }"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                        <path d="M10 11v6" />
                        <path d="M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </svg>
                  </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </main>

      <!-- ============================================================ -->
      <!-- 文件内容预览面板（支持全屏 + 语法高亮 + Markdown 渲染） -->
      <!-- ============================================================ -->
      <div v-if="viewingFile" class="modal-overlay" @click.self="closeFileViewer">
        <div
          class="modal-card file-preview-card"
          :class="{ 'file-preview-fullscreen': isFullscreen }"
        >
          <div class="detail-header">
            <h4>📄 {{ viewingFile.name }}</h4>
            <div class="detail-header-actions">
              <button class="btn-icon" :title="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
                <svg v-if="isFullscreen" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" /><line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" />
                </svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" /><line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              </button>
              <button class="btn-icon" title="关闭" @click="closeFileViewer">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
          <div class="detail-meta">
            <span>路径: {{ viewingFile.rel_path }}</span>
            <span>大小: {{ formatSize(viewingFile.size) }}</span>
            <span>修改时间: {{ formatTime(viewingFile.modified) }}</span>
            <span v-if="previewRenderMode === 'markdown'" class="render-badge">Markdown</span>
            <span v-else-if="previewRenderMode === 'highlight'" class="render-badge">Syntax {{ (_EXT_LANG_MAP[viewingFile.extension.toLowerCase()] || '').toUpperCase() }}</span>
          </div>
          <div class="file-content-area">
            <div v-if="isFileContentLoading" class="kb-loading">加载中…</div>
            <div v-else-if="!fileContent" class="kb-placeholder" style="padding: 32px 0;">
              <p>无法加载文件内容</p>
            </div>
            <div v-else-if="fileContent.message && fileContent.content === null" class="kb-placeholder" style="padding: 32px 0;">
              <p>{{ fileContent.message }}</p>
            </div>
            <!-- Markdown 渲染 -->
            <div v-else-if="previewRenderMode === 'markdown'" class="markdown-body" v-html="markdownHtml"></div>
            <!-- 语法高亮 -->
            <div v-else-if="previewRenderMode === 'highlight'" class="hljs-wrapper">
              <pre><code class="hljs" v-html="highlightHtml"></code></pre>
            </div>
            <!-- 纯文本 -->
            <pre v-else class="file-content-text">{{ fileContent.content }}</pre>
          </div>
        </div>
      </div>

      <!-- ============================================================
          弹窗：新建知识库
          ============================================================ -->
      <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal-card">
          <h4>🎲 新建知识库</h4>
          <label class="form-label">知识库名称</label>
          <input
            v-model="newKbName"
            class="form-input"
            placeholder="输入知识库名称"
            @keyup.enter="handleCreate"
          />
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="showCreateModal = false">取消</button>
            <button class="btn btn-primary" @click="handleCreate">创建</button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- 弹窗：上传 ZIP -->
      <!-- ============================================================ -->
      <div v-if="showUploadZipModal" class="modal-overlay" @click.self="showUploadZipModal = false">
        <div class="modal-card">
          <h4>📦 上传压缩包创建知识库</h4>
          <label class="form-label">选择压缩包（.zip / .tar.gz / .7z）</label>
          <input type="file" accept=".zip,.tar.gz,.tgz,.7z" class="form-input" @change="onZipFileChange" :disabled="isUploadingZip" />
          <label class="form-label">知识库名称（可选，默认使用文件名）</label>
          <input
            v-model="uploadZipName"
            class="form-input"
            placeholder="留空则使用压缩包名称"
            :disabled="isUploadingZip"
          />
          <!-- 进度条 -->
          <div v-if="isUploadingZip" class="upload-progress">
            <div class="upload-progress-bar" :style="{ width: uploadZipProgress + '%' }"></div>
            <span class="upload-progress-text">{{ uploadZipProgress }}%</span>
          </div>
          <div class="modal-actions">
            <button class="btn btn-secondary" :disabled="isUploadingZip" @click="showUploadZipModal = false">取消</button>
            <button class="btn btn-primary" :disabled="!uploadZipFile || isUploadingZip" @click="handleUploadZip">
              {{ isUploadingZip ? '上传中…' : '上传并解压' }}
            </button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- 弹窗：上传文档 -->
      <!-- ============================================================ -->
      <div v-if="showUploadFileModal" class="modal-overlay" @click.self="showUploadFileModal = false">
        <div class="modal-card">
          <h4>⬆️ 上传文档到 "{{ selectedKb }}"</h4>
          <p v-if="currentPath" class="upload-path-hint">📂 {{ currentPath }}</p>
          <p v-else class="upload-path-hint">📂 根目录</p>
          <label class="form-label">选择文件</label>
          <input type="file" class="form-input" @change="onKbFileChange" />
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="showUploadFileModal = false">取消</button>
            <button class="btn btn-primary" :disabled="!uploadKbFileTarget" @click="handleUploadFile">
              上传
            </button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- 弹窗：删除知识库确认 -->
      <!-- ============================================================ -->
      <div v-if="showDeleteKbConfirm" class="modal-overlay" @click.self="showDeleteKbConfirm = null">
        <div class="modal-card modal-card-sm">
          <h4>⚠️ 确认删除</h4>
          <p>确定要删除知识库 "<strong>{{ showDeleteKbConfirm }}</strong>" 吗？此操作不可恢复。</p>
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="showDeleteKbConfirm = null">取消</button>
            <button class="btn btn-danger" @click="handleDeleteKb(showDeleteKbConfirm!)">确认删除</button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- 弹窗：删除文件/目录确认 -->
      <!-- ============================================================ -->
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = null">
        <div class="modal-card modal-card-sm">
          <h4>⚠️ 确认删除{{ showDeleteConfirm.isDir ? '目录' : '文件' }}</h4>
          <p>
            确定要删除{{ showDeleteConfirm.isDir ? '目录' : '文件' }}
            "<strong>{{ showDeleteConfirm.name }}</strong>" 吗？
            <template v-if="showDeleteConfirm.isDir">目录内所有文件将一并删除。</template>
          </p>
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="showDeleteConfirm = null">取消</button>
            <button class="btn btn-danger" @click="handleDeleteItem({
              name: showDeleteConfirm.name,
              rel_path: showDeleteConfirm.relPath,
              is_dir: showDeleteConfirm.isDir,
            } as KbFileInfo)">确认删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- Toast 消息 -->
    <!-- ============================================================ -->
    <div class="toast-container">
      <transition-group name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="'toast-' + toast.type"
        >
          <span class="toast-icon">{{ toast.type === 'success' ? '✅' : '❌' }}</span>
          <span class="toast-msg">{{ toast.message }}</span>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style>
/* 全局样式：highlight.js 主题 */
@import 'highlight.js/styles/github.css';

[data-theme="dark"] .hljs {
  background: #1e1e2e;
  color: #cdd6f4;
}
[data-theme="dark"] .hljs-keyword { color: #cba6f7; }
[data-theme="dark"] .hljs-string { color: #a6e3a1; }
[data-theme="dark"] .hljs-number { color: #fab387; }
[data-theme="dark"] .hljs-comment { color: #6c7086; }
[data-theme="dark"] .hljs-title { color: #89b4fa; }
[data-theme="dark"] .hljs-built_in { color: #f38ba8; }
[data-theme="dark"] .hljs-attr { color: #89dceb; }
[data-theme="dark"] .hljs-params { color: #f5c2e7; }
[data-theme="dark"] .hljs-literal { color: #fab387; }
[data-theme="dark"] .hljs-type { color: #f9e2af; }
</style>

<style scoped>
/* ============================================================
   外层容器 — 匹配 KbWorkflow 的 height: 100% 模式
   ============================================================ */
.kb-management {
  height: 100%;
}

.kb-layout {
  display: flex;
  gap: 24px;
  height: 100%;
}

/* ============================================================
   左侧边栏 — 匹配 KbWorkflow 侧边栏样式
   ============================================================ */
.kb-sidebar {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--border-color);
  padding-right: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kb-sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.kb-list {
  flex: 1;
  overflow-y: auto;
}

.kb-empty {
  text-align: center;
  color: var(--text-secondary);
  padding: 24px 0;
  font-size: 13px;
}

.kb-item {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  color: var(--text-primary);
}

.kb-item:hover {
  background: var(--bg-primary);
}

.kb-item.active {
  background: var(--accent-color);
  color: #fff;
}

.kb-item.active .kb-item-meta {
  color: rgba(255, 255, 255, 0.75);
}

.kb-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kb-item-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.kb-item-actions {
  display: flex;
  gap: 2px;
  align-items: center;
}

.kb-item-action-btn {
  opacity: 0;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  transition: opacity 0.15s, background 0.15s;
  color: var(--text-secondary);
}

.kb-item-action-btn:hover {
  background: var(--bg-primary);
}

.kb-item:hover .kb-item-action-btn {
  opacity: 1;
}

.kb-item.active .kb-item-action-btn {
  color: rgba(255, 255, 255, 0.8);
}

.kb-item.active .kb-item-action-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.25);
}

.kb-item-delete {
  color: #e74c3c;
}

.kb-item-delete:hover {
  background: rgba(231, 76, 60, 0.15);
}

.kb-item.active .kb-item-delete {
  color: rgba(255, 255, 255, 0.9);
}

.kb-item-meta {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: flex;
  justify-content: space-between;
}

.kb-sidebar-actions {
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px solid var(--border-color);
}

/* ============================================================
   右侧主区域
   ============================================================ */
.kb-main {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}

.kb-main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.kb-main-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.kb-placeholder {
  text-align: center;
  padding: 64px 20px;
  color: var(--text-secondary);
}

.kb-placeholder-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.kb-loading {
  text-align: center;
  color: var(--text-secondary);
  padding: 32px 0;
}

/* ============================================================
   面包屑
   ============================================================ */
.breadcrumb-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--bg-sidebar);
  border-radius: var(--radius-sm);
  font-size: 13px;
  overflow-x: auto;
  white-space: nowrap;
}

.breadcrumb-link {
  background: none;
  border: none;
  color: var(--accent-color);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background 0.15s;
}

.breadcrumb-link:hover {
  background: var(--bg-primary);
  text-decoration: underline;
}

.breadcrumb-sep {
  color: var(--text-secondary);
  opacity: 0.5;
}

.breadcrumb-current {
  color: var(--text-primary);
  font-weight: 600;
}

/* ============================================================
   文件/目录表格
   ============================================================ */
.kb-file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.kb-file-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 2px solid var(--border-color);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.kb-file-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  vertical-align: middle;
}

.kb-file-table tr:hover td {
  background: var(--bg-sidebar);
}

.row-dir {
  cursor: pointer;
}

.row-dir .item-name-text {
  color: var(--accent-color);
}

.item-name {
  max-width: 350px;
}

.item-name-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.item-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-size {
  white-space: nowrap;
  color: var(--text-secondary) !important;
}

.item-time {
  white-space: nowrap;
  color: var(--text-secondary) !important;
  font-size: 12px;
}

.item-action {
  text-align: left;
}

.action-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

/* ============================================================
   上传路径提示
   ============================================================ */
.upload-path-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 4px 0 12px;
  padding: 6px 10px;
  background: var(--bg-sidebar);
  border-radius: var(--radius-sm);
}

/* ============================================================
   按钮
   ============================================================ */
.btn {
  padding: 8px 14px;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.15s, opacity 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent-color);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.btn-secondary:hover:not(:disabled) {
  filter: brightness(0.95);
}

.btn-accent {
  background: var(--accent-color);
  color: #fff;
}

.btn-accent:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-danger {
  background: #e74c3c;
  color: #fff;
}

.btn-danger:hover:not(:disabled) {
  background: #c0392b;
}

.btn-delete {
  background: none;
  border: 1px solid transparent;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  color: #e74c3c;
  display: inline-flex;
  align-items: center;
  transition: background 0.15s, border-color 0.15s;
}

.btn-delete:hover {
  background: rgba(231, 76, 60, 0.1);
  border-color: rgba(231, 76, 60, 0.3);
}

.btn-download {
  background: none;
  border: 1px solid transparent;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  color: var(--accent-color);
  display: inline-flex;
  align-items: center;
  transition: background 0.15s, border-color 0.15s;
}

.btn-download:hover {
  background: rgba(78, 110, 242, 0.1);
  border-color: rgba(78, 110, 242, 0.3);
}

/* ============================================================
   弹窗
   ============================================================ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-card {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  padding: 24px;
  width: 400px;
  max-width: 90vw;
  box-shadow: var(--shadow-lg);
}

.modal-card-sm {
  width: 360px;
}

.modal-card h4 {
  margin: 0 0 16px;
  font-size: 15px;
  color: var(--text-primary);
}

.modal-card p {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
  margin-top: 12px;
}

.form-label:first-of-type {
  margin-top: 0;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-primary);
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

/* ============================================================
   Toast 消息
   ============================================================ */
.toast-container {
  position: fixed;
  top: 80px;
  right: 24px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
  max-width: 380px;
}

.toast-success {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.toast-error {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

[data-theme="dark"] .toast-success {
  background: #064e3b;
  color: #a7f3d0;
  border-color: #065f46;
}

[data-theme="dark"] .toast-error {
  background: #7f1d1d;
  color: #fecaca;
  border-color: #991b1b;
}

.toast-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.toast-msg {
  line-height: 1.4;
}

/* Toast 动画 */
.toast-enter-active {
  transition: all 0.3s ease-out;
}

.toast-leave-active {
  transition: all 0.25s ease-in;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(40px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

/* ============================================================
   暗色模式
   ============================================================ */
/* ============================================================
   文件内容预览
   ============================================================ */
.file-preview-card {
  width: 780px;
  max-width: 92vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.file-preview-card .detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.file-preview-card .detail-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.file-preview-card .btn-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.file-preview-card .btn-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.file-preview-card .detail-meta {
  display: flex;
  gap: 20px;
  padding: 10px 20px;
  font-size: 12px;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.file-content-area {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  min-height: 200px;
}

.file-content-text {
  margin: 0;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  tab-size: 2;
}

/* 全屏模式 */
.file-preview-fullscreen {
  width: 96vw !important;
  max-width: 96vw !important;
  height: 94vh !important;
  max-height: 94vh !important;
}

.file-preview-fullscreen .file-content-area {
  flex: 1;
  overflow: auto;
}

/* 头部操作按钮组 */
.detail-header-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.btn-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-icon:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 渲染方式标签 */
.render-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 8px;
  background: var(--accent-color);
  color: #fff;
  font-weight: 500;
}

/* 语法高亮包装器 */
.hljs-wrapper {
  margin: 0;
}

.hljs-wrapper pre {
  margin: 0;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  background: #f6f8fa;
}

[data-theme="dark"] .hljs-wrapper pre {
  background: #1e1e2e;
}

.hljs-wrapper code {
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  tab-size: 2;
}

/* Markdown 渲染 */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin: 20px 0 10px;
  font-weight: 600;
  line-height: 1.3;
}
.markdown-body h1 { font-size: 22px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }
.markdown-body h2 { font-size: 18px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body p { margin: 0 0 12px; }
.markdown-body ul, .markdown-body ol { margin: 0 0 12px; padding-left: 24px; }
.markdown-body li { margin: 4px 0; }
.markdown-body blockquote {
  margin: 0 0 12px;
  padding: 4px 14px;
  border-left: 4px solid var(--accent-color);
  color: var(--text-secondary);
  background: var(--bg-sidebar);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.markdown-body code:not(.hljs) {
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--bg-sidebar);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 0.9em;
  color: var(--accent-color);
}
.markdown-body pre { margin: 0 0 12px; border-radius: var(--radius-sm); overflow-x: auto; }
.markdown-body pre code { background: none; padding: 0; color: inherit; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 0 0 12px; }
.markdown-body th, .markdown-body td { border: 1px solid var(--border-color); padding: 6px 12px; text-align: left; }
.markdown-body th { background: var(--bg-sidebar); font-weight: 600; }
.markdown-body hr { border: none; border-top: 1px solid var(--border-color); margin: 20px 0; }
.markdown-body a { color: var(--accent-color); }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body img { max-width: 100%; }


/* 查看按钮 */
.btn-view {
  background: none;
  border: 1px solid transparent;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  transition: background 0.15s, border-color 0.15s;
}

.btn-view:hover {
  background: rgba(78, 110, 242, 0.1);
  border-color: rgba(78, 110, 242, 0.3);
  color: var(--accent-color);
}

[data-theme="dark"] .kb-file-table tr:hover td {
  background: var(--bg-sidebar);
}

[data-theme="dark"] .breadcrumb-bar {
  background: var(--bg-sidebar);
}

/* ============================================================
   上传进度条
   ============================================================ */
.upload-progress {
  margin-top: 12px;
  height: 24px;
  background: var(--bg-sidebar);
  border-radius: var(--radius-sm);
  position: relative;
  overflow: hidden;
}

.upload-progress-bar {
  height: 100%;
  background: var(--accent-color);
  border-radius: var(--radius-sm);
  transition: width 0.3s ease;
}

.upload-progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
</style>
