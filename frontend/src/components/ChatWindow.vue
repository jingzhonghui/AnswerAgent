<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import mermaid from 'mermaid'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import type { ThinkingStep } from '@/types'
const authStore = useAuthStore()
const chatStore = useChatStore()

// 初始化 mermaid（默认配置，后续在渲染时覆盖 theme）
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  flowchart: { useMaxWidth: true },
  sequence: { useMaxWidth: true },
})

// 消息列表容器引用和自动滚动逻辑
const messagesContainer = ref<HTMLElement | null>(null)
const userScrolledUp = ref(false)
const SCROLL_THRESHOLD = 60 // 距底部多少像素以内视为"在底部"

// ===== 目录导航：用户提问小圆点 =====
interface UserQuestionDot {
  index: number       // 消息在 activeMessages 中的索引
  content: string     // 完整问题文本
  shortContent: string // 截断后的问题文本（用于 tooltip 显示）
}

const userQuestions = computed<UserQuestionDot[]>(() => {
  return chatStore.activeMessages
    .map((msg, index) => ({ msg, index }))
    .filter(({ msg }) => msg.role === 'user')
    .map(({ msg, index }) => ({
      index,
      content: msg.content,
      shortContent: msg.content.length > 30 ? msg.content.slice(0, 30) + '…' : msg.content,
    }))
})

const activeDotIndex = ref(0)
let dotObserver: IntersectionObserver | null = null

function setupDotObserver(): void {
  cleanupDotObserver()
  const container = messagesContainer.value
  if (!container) return

  // 收集所有用户消息 DOM 元素
  const userRows = container.querySelectorAll<HTMLElement>('.message-row.user')
  if (!userRows.length) return

  // 记录每个用户消息元素距离视口顶部的距离，找出最接近顶部（已滚过）的那个
  const updateActiveDot = () => {
    const containerRect = container.getBoundingClientRect()
    let closestIdx = -1
    let closestDist = Infinity

    userRows.forEach((row) => {
      const idx = Number(row.dataset.userMsgIndex)
      if (isNaN(idx)) return
      const rect = row.getBoundingClientRect()
      // 元素顶部到容器顶部的距离（负值 = 已滚过视口上方）
      const distFromTop = rect.top - containerRect.top
      // 选择最接近容器顶部且在可见范围内的
      if (distFromTop <= 80 && distFromTop > -rect.height && Math.abs(distFromTop) < closestDist) {
        closestDist = Math.abs(distFromTop)
        closestIdx = idx
      }
    })

    if (closestIdx >= 0) {
      // 找到这个 user row 在 userQuestions 中的序号
      const dotIdx = userQuestions.value.findIndex(q => q.index === closestIdx)
      if (dotIdx >= 0) {
        activeDotIndex.value = dotIdx
      }
    }
  }

  // 使用 IntersectionObserver 作为主要跟踪 + scroll 事件更新
  dotObserver = new IntersectionObserver(
    () => updateActiveDot(),
    { root: container, rootMargin: '-60px 0px 0px 0px', threshold: 0 },
  )
  userRows.forEach(row => dotObserver!.observe(row))

  // 附加滚动监听用于精确定位
  container.addEventListener('scroll', updateActiveDot, { passive: true })
  // 保存清理函数引用
  ;(container as any).__dotScrollHandler = updateActiveDot
}

function cleanupDotObserver(): void {
  if (dotObserver) {
    dotObserver.disconnect()
    dotObserver = null
  }
  const container = messagesContainer.value
  if (container && (container as any).__dotScrollHandler) {
    container.removeEventListener('scroll', (container as any).__dotScrollHandler)
    ;(container as any).__dotScrollHandler = null
  }
}

function scrollToMessage(msgIndex: number): void {
  const container = messagesContainer.value
  if (!container) return

  const row = container.querySelector<HTMLElement>(`.message-row.user[data-user-msg-index="${msgIndex}"]`)
  if (!row) return

  const containerRect = container.getBoundingClientRect()
  const rowRect = row.getBoundingClientRect()
  // 滚动使该消息对齐到容器顶部偏下一点
  const offset = rowRect.top - containerRect.top + container.scrollTop - 80
  container.scrollTo({ top: offset, behavior: 'smooth' })
}

function isNearBottom(): boolean {
  const el = messagesContainer.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD
}

function scrollToBottom(smooth = false): void {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
}

function handleScroll(): void {
  if (isNearBottom()) {
    userScrolledUp.value = false
  } else {
    userScrolledUp.value = true
  }
}

// 监听消息内容变化：生成中自动滚动，完成后渲染 mermaid
watch(
  () => chatStore.activeMessages.map(m => m.content),
  () => {
    if (chatStore.isStreaming && !userScrolledUp.value) {
      nextTick(() => scrollToBottom(false))
    } else if (!chatStore.isStreaming) {
      nextTick(() => onMessageRendered())
    }
  },
  { deep: false },
)

// 发送消息时立即滚到底部，完成后渲染 mermaid
watch(
  () => chatStore.activeMessages.length,
  (newLen, oldLen) => {
    const isNewMessage = oldLen !== undefined && newLen > oldLen
    if (isNewMessage && chatStore.isStreaming) {
      // 用户发送新消息时强制滚到底部（忽略 userScrolledUp）
      nextTick(() => scrollToBottom(false))
    } else if (!userScrolledUp.value) {
      nextTick(() => scrollToBottom(false))
    }
    // 加载已有对话（非流式）时渲染 mermaid
    if (!chatStore.isStreaming) {
      nextTick(() => onMessageRendered())
    }
  },
)

// 流式结束时强制渲染 mermaid（解决最后一个 token 为空时内容 watcher 不触发的问题）
watch(
  () => chatStore.isStreaming,
  (streaming) => {
    if (!streaming) {
      nextTick(() => onMessageRendered())
    }
  },
)

// 组件挂载时如有消息则滚到底部并渲染 mermaid
onMounted(() => {
  if (chatStore.activeMessages.length > 0) {
    nextTick(() => {
      scrollToBottom(false)
      onMessageRendered()
    })
  }
  document.addEventListener('keydown', handleFullscreenKeydown)
})

onUnmounted(() => {
  cleanupDotObserver()
  document.removeEventListener('keydown', handleFullscreenKeydown)
})

let mermaidIdCounter = 0
// Mermaid 渲染队列（避免并发问题）
let mermaidRenderQueue = Promise.resolve()

// ===== Mermaid 全屏弹窗状态 =====
const fullscreenMermaid = ref({ code: '', visible: false })
const fullscreenMermaidRef = ref<HTMLElement | null>(null)
let fullscreenMermaidRendered = false

// 缩放与拖拽
const fsScale = ref(1)
const fsTranslateX = ref(0)
const fsTranslateY = ref(0)
let fsIsDragging = false
let fsDragStartX = 0
let fsDragStartY = 0
let fsLastTranslateX = 0
let fsLastTranslateY = 0

const zoomTransformStyle = computed(() => ({
  transform: `translate(${fsTranslateX.value}px, ${fsTranslateY.value}px) scale(${fsScale.value})`,
  transformOrigin: 'center center',
  cursor: fsIsDragging ? 'grabbing' : fsScale.value > 1 ? 'grab' : 'default',
}))

function fsZoomIn(): void {
  fsScale.value = Math.min(fsScale.value + 0.25, 5)
}

function fsZoomOut(): void {
  fsScale.value = Math.max(fsScale.value - 0.25, 0.25)
}

function fsResetZoom(): void {
  fsScale.value = 1
  fsTranslateX.value = 0
  fsTranslateY.value = 0
}

function fsStartDrag(e: MouseEvent): void {
  if (fsScale.value <= 1) return
  fsIsDragging = true
  fsDragStartX = e.clientX
  fsDragStartY = e.clientY
  fsLastTranslateX = fsTranslateX.value
  fsLastTranslateY = fsTranslateY.value
}

function fsOnDrag(e: MouseEvent): void {
  if (!fsIsDragging) return
  fsTranslateX.value = fsLastTranslateX + (e.clientX - fsDragStartX)
  fsTranslateY.value = fsLastTranslateY + (e.clientY - fsDragStartY)
}

function fsEndDrag(): void {
  fsIsDragging = false
}

function fsOnWheel(e: WheelEvent): void {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.15 : 0.15
  const newScale = Math.max(0.25, Math.min(5, fsScale.value + delta))

  // 以光标位置为中心缩放
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  const ratio = newScale / fsScale.value
  fsTranslateX.value = cx - ratio * (cx - fsTranslateX.value)
  fsTranslateY.value = cy - ratio * (cy - fsTranslateY.value)
  fsScale.value = newScale
}

async function openMermaidFullscreen(code: string): Promise<void> {
  fullscreenMermaid.value = { code, visible: true }
  fullscreenMermaidRendered = false
  await nextTick()
  await renderFullscreenMermaid()
}

function closeMermaidFullscreen(): void {
  fullscreenMermaid.value = { code: '', visible: false }
  fullscreenMermaidRendered = false
  fsResetZoom()
}

async function renderFullscreenMermaid(): Promise<void> {
  if (!fullscreenMermaidRef.value || fullscreenMermaidRendered) return
  const code = fullscreenMermaid.value.code
  if (!code) return

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
  await mermaid.initialize({
    theme: isDark ? 'dark' : 'default',
    flowchart: { useMaxWidth: true },
    sequence: { useMaxWidth: false },
    themeVariables: isDark ? {
      primaryColor: '#2a2a2a',
      primaryTextColor: '#f0f0f0',
      primaryBorderColor: '#4a4a4a',
      lineColor: '#666',
      secondaryColor: '#333',
      tertiaryColor: '#252525',
    } : {
      primaryColor: '#f9f9f9',
      primaryTextColor: '#1a1a1a',
      primaryBorderColor: '#ddd',
      lineColor: '#aaa',
      secondaryColor: '#f0f0f0',
      tertiaryColor: '#fff',
    },
  })

  const id = `mermaid-fullscreen-${++mermaidIdCounter}`
  try {
    const { svg } = await mermaid.render(id, code)
    // 只移除根 <svg> 的固定宽高，让 CSS 按全屏容器自适应缩放；
    // 不能全局删除 width/height，否则会破坏 Mermaid 内部 rect/label 布局。
    let fixedSvg = svg.replace(/viewBox="NaN[^"]*"/g, 'viewBox="0 0 800 400"')
    fixedSvg = fixedSvg.replace(/<svg\b([^>]*)>/, (svgTag: string) =>
      svgTag.replace(/\s(width|height)="[^"]*"/g, '')
    )
    // 渲染到 zoom wrapper 内
    const zoomWrapper = fullscreenMermaidRef.value.querySelector('.mermaid-zoom-inner') || fullscreenMermaidRef.value
    zoomWrapper.innerHTML = fixedSvg

    // 动态插入的 SVG 不一定能被 scoped CSS 命中，直接设置属性更可靠
    const svgEl = zoomWrapper.querySelector('svg')
    if (svgEl) {
      svgEl.removeAttribute('width')
      svgEl.removeAttribute('height')
      svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet')
      svgEl.style.width = '100%'
      svgEl.style.height = '100%'
      svgEl.style.maxWidth = '100%'
      svgEl.style.maxHeight = '100%'
      svgEl.style.display = 'block'
    }

    fullscreenMermaidRendered = true
  } catch (err) {
    console.warn('Mermaid fullscreen render failed:', err)
    const zoomWrapper = fullscreenMermaidRef.value.querySelector('.mermaid-zoom-inner') || fullscreenMermaidRef.value
    zoomWrapper.innerHTML = `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
    fullscreenMermaidRendered = true
  }
}

async function copyFullscreenCode(): Promise<void> {
  try {
    await navigator.clipboard.writeText(fullscreenMermaid.value.code)
  } catch {
    // ignore
  }
}

// 监听 ESC 关闭全屏
function handleFullscreenKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape' && fullscreenMermaid.value.visible) {
    closeMermaidFullscreen()
  }
}

// markdown-it 实例：拦截 mermaid 代码块，不经过 highlight.js
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang === 'mermaid') {
      // mermaid 代码块原样输出，由 post-render 阶段处理
      return `<div class="mermaid-container" data-mermaid-code="${encodeURIComponent(str)}"></div>`
    }
    if (lang && hljs.getLanguage(lang)) {
      try {
        return '<pre class="hljs"><code>' +
          hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
          '</code></pre>'
      } catch {
        // fall through
      }
    }
    return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'
  },
})

function renderMarkdown(text: string): string {
  return md.render(text)
}

// 渲染所有 mermaid 图表
async function renderMermaidDiagrams(container: HTMLElement): Promise<void> {
  // 流式生成中跳过 mermaid 渲染（避免不完整代码块导致报错）
  if (chatStore.isStreaming) return

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

  // 重新初始化 mermaid theme（确保跟随 theme 切换）
  // 注意：sequence 和 flowchart 不设 useMaxWidth 以避免中文内容导致 viewBox NaN
  await mermaid.initialize({
    theme: isDark ? 'dark' : 'default',
    flowchart: { useMaxWidth: true },
    sequence: { useMaxWidth: false },
    themeVariables: isDark ? {
      primaryColor: '#2a2a2a',
      primaryTextColor: '#f0f0f0',
      primaryBorderColor: '#4a4a4a',
      lineColor: '#666',
      secondaryColor: '#333',
      tertiaryColor: '#252525',
    } : {
      primaryColor: '#f9f9f9',
      primaryTextColor: '#1a1a1a',
      primaryBorderColor: '#ddd',
      lineColor: '#aaa',
      secondaryColor: '#f0f0f0',
      tertiaryColor: '#fff',
    },
  })

  const wrappers = container.querySelectorAll<HTMLDivElement>('.mermaid-container[data-mermaid-code]')
  if (!wrappers.length) return

  for (const wrapper of wrappers) {
    const code = decodeURIComponent(wrapper.dataset.mermaidCode || '')
    if (!code) continue

    // 清空占位，显示加载状态
    wrapper.innerHTML = '<div class="mermaid-loading">渲染图表中...</div>'

    const id = `mermaid-${++mermaidIdCounter}`

    // 串行化渲染，避免 mermaid 并发问题
    mermaidRenderQueue = mermaidRenderQueue.then(async () => {
      try {
        const { svg } = await mermaid.render(id, code)
        // 修复可能的 viewBox NaN 问题
        const fixedSvg = svg.replace(/viewBox="NaN[^"]*"/g, 'viewBox="0 0 800 400"')
        wrapper.innerHTML = fixedSvg
        // 添加工具栏
        addMermaidToolbar(wrapper)
      } catch (err) {
        console.warn('Mermaid render failed:', err)
        wrapper.innerHTML = `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
        // 失败时退化为代码块，添加工具栏
        wrapper.dataset.viewMode = 'source'
        addMermaidToolbar(wrapper)
      }
    })
    await mermaidRenderQueue
  }
}

// 消息渲染后的回调：渲染 mermaid + 注入复制按钮 + 初始化目录导航
function onMessageRendered(): void {
  if (!messagesContainer.value) return
  renderMermaidDiagrams(messagesContainer.value)
  // 为代码块注入复制按钮（mermaid 的复制按钮在渲染完成后由 renderMermaidDiagrams 添加）
  nextTick(() => {
    addCopyButtonsForCodeBlocks(messagesContainer.value!)
    setupDotObserver()
  })
}

// 为代码块添加复制按钮
function addCopyButtonsForCodeBlocks(container: HTMLElement): void {
  const preBlocks = container.querySelectorAll<HTMLPreElement>('pre.hljs')
  for (const pre of preBlocks) {
    if (pre.querySelector('.copy-btn')) continue
    // 跳过 mermaid 容器内的代码块（mermaid 有自己的工具栏）
    if (pre.closest('.mermaid-container')) continue

    const code = pre.querySelector('code')
    if (!code) continue

    const btn = document.createElement('button')
    btn.className = 'copy-btn'
    btn.dataset.state = 'copy'
    btn.innerHTML = COPY_ICON

    btn.addEventListener('click', async () => {
      const text = code.textContent || ''
      try {
        await navigator.clipboard.writeText(text)
        btn.dataset.state = 'copied'
        setTimeout(() => { btn.dataset.state = 'copy' }, 2000)
      } catch {
        btn.dataset.state = 'failed'
        setTimeout(() => { btn.dataset.state = 'copy' }, 2000)
      }
    })

    pre.style.position = 'relative'
    pre.appendChild(btn)
  }
}

// ===== Mermaid 工具栏：切换源码/图表、复制、全屏 =====
const MERMAID_TOGGLE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`
const MERMAID_FULLSCREEN_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`

function addMermaidToolbar(container: HTMLDivElement): void {
  // 移除旧工具栏（toggle 时会重新调用）
  const existing = container.querySelector('.mermaid-toolbar')
  if (existing) existing.remove()

  // 首次渲染时保存 SVG 内容
  if (!container.dataset.viewMode) {
    container.dataset.mermaidSvg = container.innerHTML
    container.dataset.viewMode = 'diagram'
  }

  const toolbar = document.createElement('div')
  toolbar.className = 'mermaid-toolbar'
  toolbar.innerHTML = `
    <button class="mermaid-btn toggle-btn" title="查看源码">
      ${MERMAID_TOGGLE_ICON}
    </button>
    <button class="mermaid-btn copy-btn" title="复制源码">
      ${COPY_ICON}
    </button>
    <button class="mermaid-btn fullscreen-btn" title="全屏查看">
      ${MERMAID_FULLSCREEN_ICON}
    </button>
  `

  // 切换按钮
  const toggleBtn = toolbar.querySelector('.toggle-btn')!
  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation()
    toggleMermaidView(container)
  })

  // 复制按钮
  const copyBtn = toolbar.querySelector('.copy-btn')!
  copyBtn.addEventListener('click', async (e) => {
    e.stopPropagation()
    const raw = decodeURIComponent(container.dataset.mermaidCode || '')
    if (!raw) return
    try {
      await navigator.clipboard.writeText(raw)
      copyBtn.setAttribute('data-state', 'copied')
      setTimeout(() => copyBtn.setAttribute('data-state', 'copy'), 2000)
    } catch {
      copyBtn.setAttribute('data-state', 'failed')
      setTimeout(() => copyBtn.setAttribute('data-state', 'copy'), 2000)
    }
  })

  // 全屏按钮
  const fullscreenBtn = toolbar.querySelector('.fullscreen-btn')!
  fullscreenBtn.addEventListener('click', (e) => {
    e.stopPropagation()
    const code = decodeURIComponent(container.dataset.mermaidCode || '')
    if (code) openMermaidFullscreen(code)
  })

  container.style.position = 'relative'
  container.appendChild(toolbar)
}

function toggleMermaidView(container: HTMLDivElement): void {
  const currentMode = container.dataset.viewMode || 'diagram'
  const code = decodeURIComponent(container.dataset.mermaidCode || '')

  if (currentMode === 'diagram') {
    // 切换到源码视图：保存当前 SVG，替换为代码块
    container.dataset.mermaidSvg = container.innerHTML
    container.innerHTML = `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
    container.dataset.viewMode = 'source'
  } else {
    // 切换到图表视图：恢复保存的 SVG
    const svg = container.dataset.mermaidSvg
    if (!svg) return  // 没有保存的 SVG（渲染失败等），无法切换
    container.innerHTML = svg
    container.dataset.viewMode = 'diagram'
  }

  // 重新添加工具栏
  addMermaidToolbar(container)
}

// 复制按钮 SVG 图标（剪贴板）
const COPY_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`

function formatTime(timestamp?: string): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDate(timestamp?: string): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)

  if (isToday) return '今天'
  if (date.toDateString() === yesterday.toDateString()) return '昨天'

  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
  })
}

// 获取消息时间戳（兼容 timestamp 和 created_at）
function getMsgTimestamp(msg: { timestamp?: string; created_at?: string }): string {
  return msg.timestamp || msg.created_at || ''
}

// 是否显示知识库匹配状态
const showKbStatus = computed(() => {
  return chatStore.isStreaming && chatStore.matchedKbs.length > 0
})

// 深度思考面板：是否展开
const thinkingExpanded = ref(false)
// 流式进行中自动展开，结束后可折叠
watch(
  () => chatStore.isStreaming,
  (streaming) => {
    if (streaming) {
      thinkingExpanded.value = true
    }
  },
)

function toggleThinking(): void {
  thinkingExpanded.value = !thinkingExpanded.value
}

/** 格式化思考步骤为可读文本 */
function formatThinkingStep(step: ThinkingStep): string {
  if (step.type === 'action') {
    const lines: string[] = []
    if (step.thought) {
      lines.push(step.thought)
    }
    if (step.tool) {
      lines.push(`**操作**: \`${step.tool}\``)
      lines.push(`**输入**: ${step.toolInput}`)
    }
    return lines.join('\n\n')
  }
  // observation
  return `**结果**: ${step.result}`
}
</script>

<template>
  <main class="chat-window">
    <!-- 空状态 -->
    <div v-if="!chatStore.hasActiveConversation()" class="empty-state">
      <div class="welcome">
        <div class="welcome-logo">
          <svg viewBox="0 0 1024 1024" width="40" height="40" fill="white">
            <path d="M231.936 409.6v174.592H161.792V409.6h70.144m0-34.816H161.792c-19.456 0-34.816 15.872-34.816 34.816v174.592c0 18.944 15.872 34.816 34.816 34.816h69.632c19.456 0 34.816-15.872 34.816-34.816V409.6c0.512-18.944-15.36-34.816-34.304-34.816zM860.16 409.6v174.592h-69.632V409.6H860.16m0-34.816h-69.632c-18.944 0-34.816 15.872-34.816 34.816v174.592c0 19.456 15.872 34.816 34.816 34.816H860.16c19.456 0 34.816-15.872 34.816-34.816V409.6c0-18.944-15.36-34.816-34.816-34.816z m-349.184 349.184c38.4 0 69.632 31.232 69.632 69.632s-31.232 69.632-69.632 69.632-69.632-31.232-69.632-69.632 31.232-69.632 69.632-69.632m0-34.816c-57.856 0-104.448 47.104-104.448 104.448 0 57.856 47.104 104.96 104.448 104.96s104.448-47.104 104.448-104.448-46.592-104.96-104.448-104.96zM441.344 374.784H371.2v69.632h69.632V374.784z m209.408 0h-69.632v69.632h69.632V374.784z m-19.456 174.592c-24.064 41.472-68.608 69.632-120.32 69.632s-96.256-28.16-120.32-69.632h-39.424c27.136 61.44 88.064 104.448 159.744 104.448s132.608-43.008 159.744-104.448h-39.424z"/>
            <path d="M215.04 374.784c43.52-121.856 159.232-209.408 295.936-209.408s252.416 87.552 295.936 209.408h37.376c-44.544-141.824-176.64-244.224-333.312-244.224s-288.256 102.912-332.8 244.224H215.04z m577.024 244.224c-36.352 72.704-99.328 129.024-176.128 156.16v37.376c96.768-30.208 175.104-101.376 215.04-193.536h-38.912z"/>
          </svg>
        </div>
        <h1>Answer Agent</h1>
        <p>基于本地知识库的 AI 问答助手</p>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="chatStore.isConversationLoading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <!-- 消息列表 -->
    <div v-else ref="messagesContainer" class="messages-container" @scroll="handleScroll">
      <!-- 知识库匹配状态 -->
      <div v-if="showKbStatus" class="kb-match-status">
        <span class="kb-match-label">匹配知识库:</span>
        <span
          v-for="kb in chatStore.matchedKbs"
          :key="kb"
          class="kb-badge"
        >
          {{ kb }}
        </span>
      </div>

      <div v-if="chatStore.activeMessages.length === 0" class="no-messages">
        <p>发送消息开始对话</p>
      </div>

      <template v-else>
        <div
          v-for="(msg, index) in chatStore.activeMessages"
          :key="index"
          class="message-row"
          :class="msg.role"
          :data-user-msg-index="msg.role === 'user' ? index : undefined"
        >
          <!-- 日期分隔 -->
          <div
            v-if="index === 0 || formatDate(getMsgTimestamp(msg)) !== formatDate(getMsgTimestamp(chatStore.activeMessages[index - 1]))"
            class="date-divider"
          >
            <span>{{ formatDate(getMsgTimestamp(msg)) }}</span>
          </div>

          <!-- 助手消息（左侧） -->
          <div v-if="msg.role === 'assistant'" class="message-content-wrapper assistant">
            <div class="message-avatar assistant-avatar">
              <svg viewBox="0 0 1024 1024" width="18" height="18" fill="currentColor">
                <path d="M231.936 409.6v174.592H161.792V409.6h70.144m0-34.816H161.792c-19.456 0-34.816 15.872-34.816 34.816v174.592c0 18.944 15.872 34.816 34.816 34.816h69.632c19.456 0 34.816-15.872 34.816-34.816V409.6c0.512-18.944-15.36-34.816-34.304-34.816zM860.16 409.6v174.592h-69.632V409.6H860.16m0-34.816h-69.632c-18.944 0-34.816 15.872-34.816 34.816v174.592c0 19.456 15.872 34.816 34.816 34.816H860.16c19.456 0 34.816-15.872 34.816-34.816V409.6c0-18.944-15.36-34.816-34.816-34.816z m-349.184 349.184c38.4 0 69.632 31.232 69.632 69.632s-31.232 69.632-69.632 69.632-69.632-31.232-69.632-69.632 31.232-69.632 69.632-69.632m0-34.816c-57.856 0-104.448 47.104-104.448 104.448 0 57.856 47.104 104.96 104.448 104.96s104.448-47.104 104.448-104.448-46.592-104.96-104.448-104.96zM441.344 374.784H371.2v69.632h69.632V374.784z m209.408 0h-69.632v69.632h69.632V374.784z m-19.456 174.592c-24.064 41.472-68.608 69.632-120.32 69.632s-96.256-28.16-120.32-69.632h-39.424c27.136 61.44 88.064 104.448 159.744 104.448s132.608-43.008 159.744-104.448h-39.424z"/>
                <path d="M215.04 374.784c43.52-121.856 159.232-209.408 295.936-209.408s252.416 87.552 295.936 209.408h37.376c-44.544-141.824-176.64-244.224-333.312-244.224s-288.256 102.912-332.8 244.224H215.04z m577.024 244.224c-36.352 72.704-99.328 129.024-176.128 156.16v37.376c96.768-30.208 175.104-101.376 215.04-193.536h-38.912z"/>
              </svg>
            </div>
            <div class="message-body assistant">
              <div class="message-author-row">
                <span class="message-author">Answer Agent</span>
                <span class="message-time">{{ formatTime(getMsgTimestamp(msg)) }}</span>
              </div>

              <!-- 深度思考面板 -->
              <div
                v-if="(chatStore.thinkingSteps.length > 0 && index === chatStore.activeMessages.length - 1) || (msg.thinking_steps && msg.thinking_steps.length > 0)"
                class="thinking-panel"
              >
                <div class="thinking-header" @click="toggleThinking">
                  <svg
                    class="thinking-chevron"
                    :class="{ expanded: thinkingExpanded }"
                    viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"
                  >
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                  <span class="thinking-title">
                    🤔 深度思考
                    <span class="thinking-step-count">
                      ({{ (index === chatStore.activeMessages.length - 1 && chatStore.thinkingSteps.length > 0 ? chatStore.thinkingSteps : msg.thinking_steps || []).filter((s: ThinkingStep) => s.type === 'action').length }} 步推理)
                    </span>
                  </span>
                  <span v-if="chatStore.isStreaming && index === chatStore.activeMessages.length - 1" class="thinking-spinner"></span>
                </div>
                <div v-show="thinkingExpanded" class="thinking-body">
                  <div
                    v-for="(step, si) in (index === chatStore.activeMessages.length - 1 && chatStore.thinkingSteps.length > 0 ? chatStore.thinkingSteps : msg.thinking_steps || [])"
                    :key="si"
                    class="thinking-step"
                    :class="step.type"
                  >
                    <div class="thinking-step-header">
                      <span class="step-badge" :class="step.type">
                        {{ step.type === 'action' ? '💡 推理' : '📋 结果' }}
                      </span>
                      <span v-if="step.tool" class="step-tool">{{ step.tool }}</span>
                    </div>
                    <div
                      class="thinking-step-content markdown-body"
                      v-html="renderMarkdown(formatThinkingStep(step))"
                    ></div>
                  </div>
                </div>
              </div>

              <div class="message-bubble assistant-bubble">
                <div
                  v-if="msg.content"
                  class="message-text markdown-body"
                  v-html="renderMarkdown(msg.content)"
                />
                <span
                  v-if="chatStore.isStreaming && index === chatStore.activeMessages.length - 1 && !chatStore.thinkingSteps.length"
                  class="streaming-cursor"
                >▌</span>
              </div>
              <!-- 引用文件 -->
              <div
                v-if="msg.files_used && msg.files_used.length > 0"
                class="message-files"
              >
                <span class="files-label">参考文件:</span>
                <span
                  v-for="file in msg.files_used"
                  :key="file.file_path"
                  class="file-tag"
                >
                  {{ file.file_path }}
                </span>
              </div>
            </div>
          </div>

          <!-- 用户消息（右侧） -->
          <div v-else class="message-content-wrapper user">
            <div class="message-body user">
              <div class="message-bubble user-bubble">
                <div class="message-text">
                  {{ msg.content }}
                </div>
              </div>
            </div>
            <div class="message-avatar user-avatar">
              <span>{{ authStore.user?.username?.charAt(0).toUpperCase() || 'U' }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 目录导航：用户提问小圆点 -->
    <div
      v-if="userQuestions.length > 1"
      class="dot-nav"
    >
      <div
        v-for="(q, qi) in userQuestions"
        :key="qi"
        class="dot-nav-item"
        :class="{ active: qi === activeDotIndex }"
        @click="scrollToMessage(q.index)"
      >
        <div class="dot"></div>
        <span class="dot-tooltip">{{ q.shortContent }}</span>
      </div>
    </div>
  </main>

    <!-- Mermaid 全屏弹窗 -->
    <Teleport to="body">
      <div
        v-if="fullscreenMermaid.visible"
        class="mermaid-fullscreen-overlay"
        @click.self="closeMermaidFullscreen"
      >
        <div class="mermaid-fullscreen-card">
          <div class="mermaid-fullscreen-header">
            <span class="mermaid-fullscreen-title">Mermaid 图表</span>
            <div class="mermaid-fullscreen-actions">
              <!-- 缩放控制 -->
              <button class="mermaid-fs-btn" title="缩小" @click="fsZoomOut">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </button>
              <span class="mermaid-fs-zoom-level">{{ Math.round(fsScale * 100) }}%</span>
              <button class="mermaid-fs-btn" title="放大" @click="fsZoomIn">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </button>
              <button class="mermaid-fs-btn" title="重置" @click="fsResetZoom">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
              </button>
              <span class="mermaid-fs-divider"></span>
              <button
                class="mermaid-fs-btn"
                title="复制源码"
                @click="copyFullscreenCode"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
              <button
                class="mermaid-fs-btn mermaid-fs-close"
                title="关闭 (ESC)"
                @click="closeMermaidFullscreen"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
          <div
            class="mermaid-fullscreen-body"
            @mousedown="fsStartDrag"
            @mousemove="fsOnDrag"
            @mouseup="fsEndDrag"
            @mouseleave="fsEndDrag"
            @wheel.prevent="fsOnWheel"
          >
            <div ref="fullscreenMermaidRef" class="mermaid-zoom-wrapper" :style="zoomTransformStyle">
              <div class="mermaid-zoom-inner">
                <div class="mermaid-loading">渲染图表中...</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
</template>

<style scoped>
.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome {
  text-align: center;
  padding: 40px;
}

.welcome-logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-color);
  border-radius: var(--radius-lg);
  font-size: 28px;
  color: white;
}

.welcome h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.welcome p {
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0;
}

/* 加载中 */
.loading-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 知识库匹配状态 */
.kb-match-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18%;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.kb-match-label {
  font-size: 14px;
  color: var(--text-tertiary);
}

.kb-badge {
  display: inline-block;
  padding: 4px 10px;
  background: rgba(78, 110, 242, 0.1);
  color: var(--accent-color);
  font-size: 13px;
  border-radius: var(--radius-full);
  border: 1px solid rgba(78, 110, 242, 0.2);
}

/* 消息容器 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 0;
}

.no-messages {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* ===== 气泡对话布局 ===== */

/* 消息行 */
.message-row {
  padding: 6px 18%;
}

.message-content-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 100%;
}

/* 用户消息 -> 右对齐 */
.message-content-wrapper.user {
  justify-content: flex-end;
}

/* 助手消息 -> 左对齐 */
.message-content-wrapper.assistant {
  justify-content: flex-start;
}

/* 头像 - 圆形 */
.message-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 600;
  position: sticky;
  top: 0;
}

.assistant-avatar {
  background: var(--accent-color);
  color: white;
}

.user-avatar {
  background: #10a37f;
  color: white;
}

/* 消息体容器 */
.message-body {
  display: flex;
  flex-direction: column;
  max-width: 70%;
  min-width: 0;
}

.message-body.assistant {
  align-items: flex-start;
}

.message-body.user {
  align-items: flex-end;
}

/* 助手名称行 */
.message-author-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  padding-left: 4px;
}

.message-author {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 气泡 */
.message-bubble {
  padding: 10px 16px;
  line-height: 1.6;
  word-break: break-word;
}

.assistant-bubble {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: 4px 16px 16px 16px;
  color: var(--text-primary);
}

.user-bubble {
  background: var(--accent-color);
  border-radius: 16px 4px 16px 16px;
  color: #ffffff;
}

.message-text {
  font-size: 16px;
  white-space: pre-wrap;
}

.user-bubble .message-text {
  color: #ffffff;
}

/* 流式光标 */
.streaming-cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent-color);
  font-size: 16px;
  font-weight: bold;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* markdown 渲染样式 */
.assistant-bubble .markdown-body {
  white-space: normal;
}

.assistant-bubble .markdown-body :deep(p) {
  margin: 0 0 8px;
}

.assistant-bubble .markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

/* 内联代码 */
.assistant-bubble .markdown-body :deep(code) {
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 4px;
  font-size: 14px;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  color: inherit;
}

[data-theme="dark"] .assistant-bubble .markdown-body :deep(code) {
  background: rgba(255, 255, 255, 0.1);
}

.assistant-bubble .markdown-body :deep(pre) {
  margin: 8px 0;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

/* 代码块：浅色模式覆盖 github-dark.css */
.assistant-bubble .markdown-body :deep(pre code.hljs),
.assistant-bubble .markdown-body :deep(pre code) {
  display: block;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.5;
  color: #24292f !important;
  background: #f6f8fa !important;
}

[data-theme="dark"] .assistant-bubble .markdown-body :deep(pre code.hljs),
[data-theme="dark"] .assistant-bubble .markdown-body :deep(pre code) {
  color: #c9d1d9 !important;
  background: #0d1117 !important;
}

.assistant-bubble .markdown-body :deep(ul),
.assistant-bubble .markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.assistant-bubble .markdown-body :deep(li) {
  margin: 2px 0;
}

.assistant-bubble .markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--accent-color);
  color: var(--text-secondary);
}

.assistant-bubble .markdown-body :deep(a) {
  color: var(--accent-color);
  text-decoration: none;
}

.assistant-bubble .markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.assistant-bubble .markdown-body :deep(strong) {
  font-weight: 600;
}

/* Markdown 表格 */
.assistant-bubble .markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 15px;
  overflow-x: auto;
  display: block;
}

.assistant-bubble .markdown-body :deep(th),
.assistant-bubble .markdown-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
  line-height: 1.5;
}

.assistant-bubble .markdown-body :deep(th) {
  background: var(--bg-hover);
  font-weight: 600;
  color: var(--text-primary);
}

.assistant-bubble .markdown-body :deep(td) {
  color: var(--text-secondary);
}

.assistant-bubble .markdown-body :deep(tr:nth-child(even) td) {
  background: var(--bg-hover);
}

/* Mermaid 图表 */
.assistant-bubble .markdown-body :deep(.mermaid-container) {
  margin: 12px 0;
  overflow-x: auto;
  text-align: center;
  background: var(--bg-primary);
  border-radius: var(--radius-sm);
  padding: 16px;
}

.assistant-bubble .markdown-body :deep(.mermaid-container svg) {
  max-width: 100%;
  height: auto;
}

.assistant-bubble .markdown-body :deep(.mermaid-loading) {
  padding: 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* 暗色主题下 mermaid 由 reinitialize 的 dark theme 处理 */

/* 复制按钮 */
.assistant-bubble .markdown-body :deep(.copy-btn) {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  padding: 5px;
  color: var(--text-tertiary);
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, color 0.2s;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.assistant-bubble .markdown-body :deep(.copy-btn svg) {
  width: 16px;
  height: 16px;
}

.assistant-bubble .markdown-body :deep(pre:hover .copy-btn) {
  opacity: 1;
}

.assistant-bubble .markdown-body :deep(.copy-btn:hover) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.assistant-bubble .markdown-body :deep(.copy-btn[data-state="copied"]) {
  color: #10b981;
  border-color: #10b981;
}

.assistant-bubble .markdown-body :deep(.copy-btn[data-state="failed"]) {
  color: #ef4444;
  border-color: #ef4444;
}

/* ===== Mermaid 工具栏 ===== */
.assistant-bubble .markdown-body :deep(.mermaid-toolbar) {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.2s;
}

.assistant-bubble .markdown-body :deep(.mermaid-container:hover .mermaid-toolbar) {
  opacity: 1;
}

/* 覆盖全局 .copy-btn 的 absolute 定位，让工具栏内部的按钮正常排列 */
.assistant-bubble .markdown-body :deep(.mermaid-toolbar .copy-btn) {
  position: static;
  opacity: 1;
}

.assistant-bubble .markdown-body :deep(.mermaid-btn) {
  width: 28px;
  height: 28px;
  padding: 5px;
  color: var(--text-tertiary);
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.assistant-bubble .markdown-body :deep(.mermaid-btn:hover) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.assistant-bubble .markdown-body :deep(.mermaid-btn svg) {
  width: 16px;
  height: 16px;
}

.assistant-bubble .markdown-body :deep(.mermaid-btn.copy-btn[data-state="copied"]) {
  color: #10b981;
  border-color: #10b981;
}

.assistant-bubble .markdown-body :deep(.mermaid-btn.copy-btn[data-state="failed"]) {
  color: #ef4444;
  border-color: #ef4444;
}

/* 引用文件 */
.message-files {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 4px 0;
}

.files-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.file-tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-size: 13px;
  border-radius: var(--radius-sm);
  font-family: monospace;
}

/* 日期分隔 */
.date-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 24px 0 16px;
}

.date-divider span {
  padding: 4px 12px;
  background: var(--bg-hover);
  color: var(--text-tertiary);
  font-size: 13px;
  border-radius: var(--radius-full);
}

/* 响应式 */
@media (max-width: 1200px) {
  .message-row {
    padding: 6px 12%;
  }
  .kb-match-status {
    padding: 12px 12%;
  }
}

@media (max-width: 768px) {
  .message-row {
    padding: 6px 16px;
  }
  .kb-match-status {
    padding: 12px 16px;
  }

  .message-body {
    max-width: 85%;
  }
}

/* ===== 深度思考面板 ===== */
.thinking-panel {
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  overflow: hidden;
  max-width: 100%;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.thinking-header:hover {
  background: var(--bg-hover);
}

.thinking-chevron {
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform 0.2s;
}

.thinking-chevron.expanded {
  transform: rotate(90deg);
}

.thinking-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  flex: 1;
}

.thinking-step-count {
  font-weight: 400;
  color: var(--text-tertiary);
  font-size: 13px;
}

.thinking-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.thinking-body {
  border-top: 1px solid var(--border-color);
  padding: 8px 12px;
  max-height: 400px;
  overflow-y: auto;
}

.thinking-step {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border-color);
}

.thinking-step:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.thinking-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.step-badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 600;
  border-radius: var(--radius-full);
  line-height: 1.6;
}

.step-badge.action {
  background: rgba(139, 92, 246, 0.12);
  color: #8b5cf6;
  border: 1px solid rgba(139, 92, 246, 0.25);
}

.step-badge.observation {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.step-tool {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: monospace;
  background: var(--bg-hover);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.thinking-step-content {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.thinking-step-content :deep(p) {
  margin: 0 0 4px;
}

.thinking-step-content :deep(p:last-child) {
  margin-bottom: 0;
}

/* 思考面板内联代码 */
.thinking-step-content :deep(code) {
  font-size: 13px;
  padding: 1px 4px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 3px;
  color: inherit;
}

[data-theme="dark"] .thinking-step-content :deep(code) {
  background: rgba(255, 255, 255, 0.1);
}

/* 思考面板代码块：与正式回复保持一致的浅/深色样式 */
.thinking-step-content :deep(pre) {
  margin: 4px 0;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.thinking-step-content :deep(pre code) {
  display: block;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.5;
  color: #24292f !important;
  background: #f6f8fa !important;
}

[data-theme="dark"] .thinking-step-content :deep(pre code) {
  color: #c9d1d9 !important;
  background: #0d1117 !important;
}

.thinking-step-content :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

/* 暗色主题下 badge 调整 */
[data-theme="dark"] .step-badge.action {
  background: rgba(139, 92, 246, 0.18);
}

[data-theme="dark"] .step-badge.observation {
  background: rgba(16, 185, 129, 0.18);
}

/* ===== 目录导航：用户提问小圆点 ===== */
.dot-nav {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  z-index: 10;
}

.dot-nav-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s ease;
  opacity: 0.4;
}

.dot-nav-item:hover .dot {
  width: 8px;
  height: 8px;
  background: var(--accent-color);
  opacity: 0.8;
}

.dot-nav-item.active .dot {
  width: 10px;
  height: 10px;
  background: var(--accent-color);
  opacity: 1;
  box-shadow: 0 0 6px rgba(78, 110, 242, 0.4);
}

/* tooltip：悬停显示问题文本 */
.dot-tooltip {
  position: absolute;
  right: calc(100% + 10px);
  top: 50%;
  transform: translateY(-50%);
  padding: 6px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: var(--shadow-md);
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
}

/* tooltip 小三角箭头 */
.dot-tooltip::after {
  content: '';
  position: absolute;
  left: 100%;
  top: 50%;
  transform: translateY(-50%);
  border: 5px solid transparent;
  border-left-color: var(--border-color);
}

.dot-nav-item:hover .dot-tooltip {
  opacity: 1;
}

/* ===== Mermaid 全屏弹窗 ===== */
.mermaid-fullscreen-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 40px;
}

.mermaid-fullscreen-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 1100px;
  height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

.mermaid-fullscreen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.mermaid-fullscreen-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.mermaid-fullscreen-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mermaid-fs-btn {
  width: 32px;
  height: 32px;
  padding: 6px;
  color: var(--text-tertiary);
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, color 0.2s;
}

.mermaid-fs-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.mermaid-fs-btn svg {
  width: 18px;
  height: 18px;
}

.mermaid-fs-close:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border-color: #ef4444;
}

.mermaid-fs-zoom-level {
  font-size: 13px;
  color: var(--text-secondary);
  min-width: 44px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.mermaid-fs-divider {
  width: 1px;
  height: 20px;
  background: var(--border-color);
  margin: 0 4px;
}

.mermaid-fullscreen-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  position: relative;
}

.mermaid-zoom-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
  user-select: none;
}

.mermaid-zoom-inner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.mermaid-fullscreen-body .mermaid-zoom-inner {
  width: 100%;
  height: 100%;
}

.mermaid-fullscreen-body .mermaid-zoom-inner :deep(svg) {
  width: 100% !important;
  height: 100% !important;
  max-width: 100%;
  max-height: 100%;
  display: block;
}

.mermaid-fullscreen-body .mermaid-loading {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 15px;
}

.mermaid-fullscreen-body :deep(pre.hljs) {
  width: 100%;
  margin: 0;
}

.mermaid-fullscreen-body :deep(pre code) {
  display: block;
  padding: 20px;
  font-size: 14px;
  line-height: 1.6;
  color: #24292f !important;
  background: #f6f8fa !important;
}

[data-theme="dark"] .mermaid-fullscreen-body :deep(pre code) {
  color: #c9d1d9 !important;
  background: #0d1117 !important;
}

/* 全屏弹窗响应式 */
@media (max-width: 768px) {
  .mermaid-fullscreen-overlay {
    padding: 16px;
  }

  .mermaid-fullscreen-body {
    padding: 20px;
  }
}
</style>