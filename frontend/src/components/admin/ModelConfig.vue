<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getModelConfig, updateModelConfig } from '@/api'
import type { ModelConfigItem } from '@/types'

const configs = ref<ModelConfigItem[]>([])
const isLoading = ref(false)
const isSaving = ref(false)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')

// 敏感字段（API Key）显示为密码框
const sensitiveKeys = new Set(['api_key', 'deep_api_key'])

// 需要重启才能生效的配置项
const restartRequiredKeys = new Set(['knowledge_path', 'data_path'])

// 系统配置键（非 LLM 配置）
const systemConfigKeys = new Set(['history_window', 'knowledge_path', 'data_path', 'jwt_algorithm', 'jwt_expire_minutes'])

// LLM 默认模型配置键（不含 deep_ 前缀）
const llmConfigKeys = new Set(['llm_provider', 'api_key', 'base_url', 'model', 'temperature'])

// 抽屉展开状态
const expandedDrawers = ref<Record<string, boolean>>({
  default: true,
  deep: false,
  system: false,
})

function toggleDrawer(key: string) {
  expandedDrawers.value[key] = !expandedDrawers.value[key]
}

// 分组后的配置
const defaultConfigs = computed(() => configs.value.filter(c => llmConfigKeys.has(c.key)))
const deepConfigs = computed(() => configs.value.filter(c => c.key.startsWith('deep_')))
const sysConfigs = computed(() => configs.value.filter(c => systemConfigKeys.has(c.key)))

// 下拉选择字段
const selectFields: Record<string, { value: string; label: string }[]> = {
  llm_provider: [
    { value: 'openai', label: 'OpenAI（兼容 DeepSeek 等）' },
    { value: 'anthropic', label: 'Anthropic' },
  ],
  deep_llm_provider: [
    { value: '', label: '复用默认模型提供商' },
    { value: 'openai', label: 'OpenAI（兼容 DeepSeek 等）' },
    { value: 'anthropic', label: 'Anthropic' },
  ],
  deep_model_enabled: [
    { value: 'true', label: '启用' },
    { value: 'false', label: '禁用' },
  ],
  jwt_algorithm: [
    { value: 'HS256', label: 'HS256' },
    { value: 'HS384', label: 'HS384' },
    { value: 'HS512', label: 'HS512' },
  ],
}

function isSelectField(key: string): boolean {
  return key in selectFields
}

function getSelectOptions(key: string) {
  return selectFields[key] || []
}

onMounted(async () => {
  await loadConfig()
})

async function loadConfig() {
  isLoading.value = true
  try {
    const data = await getModelConfig()
    configs.value = data.configs
  } catch {
    showMessage('加载配置失败', 'error')
  } finally {
    isLoading.value = false
  }
}

async function saveConfig() {
  isSaving.value = true
  message.value = ''
  try {
    const items = configs.value.map(c => ({ key: c.key, value: c.value }))
    await updateModelConfig(items)
    showMessage('配置已保存并即时生效', 'success')
  } catch {
    showMessage('保存失败', 'error')
  } finally {
    isSaving.value = false
  }
}

function showMessage(msg: string, type: 'success' | 'error') {
  message.value = msg
  messageType.value = type
  setTimeout(() => { message.value = '' }, 3000)
}

function getInputType(key: string): string {
  return sensitiveKeys.has(key) ? 'password' : 'text'
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>模型配置</h1>
        <p class="subtitle">配置 LLM 模型参数，修改后即时生效无需重启</p>
      </div>
      <div class="actions">
        <button class="btn btn-secondary" :disabled="isLoading" @click="loadConfig">
          刷新
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="saveConfig">
          {{ isSaving ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>

    <div v-if="message" class="message" :class="messageType">
      {{ message }}
    </div>

    <div v-if="isLoading" class="loading">加载中...</div>

    <div v-else class="drawers">
      <!-- 默认模型 -->
      <div class="drawer" :class="{ open: expandedDrawers.default }">
        <button class="drawer-header" @click="toggleDrawer('default')">
          <div class="drawer-title">
            <span class="drawer-chevron">▶</span>
            <h2>默认模型</h2>
            <span class="drawer-badge">{{ defaultConfigs.length }} 项</span>
          </div>
        </button>
        <div class="drawer-body">
          <div v-for="cfg in defaultConfigs" :key="cfg.key" class="form-row">
            <label :for="cfg.key">{{ cfg.key }}</label>
            <select
              v-if="isSelectField(cfg.key)"
              :id="cfg.key"
              v-model="cfg.value"
              class="form-select"
            >
              <option v-for="opt in getSelectOptions(cfg.key)" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <input
              v-else
              :id="cfg.key"
              v-model="cfg.value"
              :type="getInputType(cfg.key)"
              class="form-input"
            />
            <span class="form-hint">{{ cfg.description }}</span>
          </div>
        </div>
      </div>

      <!-- 深度思考模型 -->
      <div class="drawer" :class="{ open: expandedDrawers.deep }">
        <button class="drawer-header" @click="toggleDrawer('deep')">
          <div class="drawer-title">
            <span class="drawer-chevron">▶</span>
            <h2>深度思考模型</h2>
            <span class="drawer-badge">{{ deepConfigs.length }} 项</span>
          </div>
          <span class="drawer-desc">深度思考模式使用独立的模型配置，可与默认模型完全不同</span>
        </button>
        <div class="drawer-body">
          <div v-for="cfg in deepConfigs" :key="cfg.key" class="form-row">
            <label :for="cfg.key">
              {{ cfg.key }}
              <span v-if="cfg.restart_required" class="restart-badge">需重启</span>
            </label>
            <select
              v-if="isSelectField(cfg.key)"
              :id="cfg.key"
              v-model="cfg.value"
              class="form-select"
            >
              <option v-for="opt in getSelectOptions(cfg.key)" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <input
              v-else
              :id="cfg.key"
              v-model="cfg.value"
              :type="getInputType(cfg.key)"
              class="form-input"
            />
            <span class="form-hint">{{ cfg.description }}</span>
          </div>
        </div>
      </div>

      <!-- 系统配置 -->
      <div v-if="sysConfigs.length" class="drawer" :class="{ open: expandedDrawers.system }">
        <button class="drawer-header" @click="toggleDrawer('system')">
          <div class="drawer-title">
            <span class="drawer-chevron">▶</span>
            <h2>系统配置</h2>
            <span class="drawer-badge">{{ sysConfigs.length }} 项</span>
          </div>
          <span class="drawer-desc">通用系统设置（带"需重启"标记的项需重启服务后生效）</span>
        </button>
        <div class="drawer-body">
          <div v-for="cfg in sysConfigs" :key="cfg.key" class="form-row">
            <label :for="cfg.key">
              {{ cfg.key }}
              <span v-if="cfg.restart_required" class="restart-badge">需重启</span>
            </label>
            <select
              v-if="isSelectField(cfg.key)"
              :id="cfg.key"
              v-model="cfg.value"
              class="form-select"
            >
              <option v-for="opt in getSelectOptions(cfg.key)" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <input
              v-else-if="cfg.key === 'history_window'"
              :id="cfg.key"
              v-model.number="cfg.value"
              type="number"
              min="1"
              max="50"
              class="form-input"
            />
            <input
              v-else
              :id="cfg.key"
              v-model="cfg.value"
              type="text"
              class="form-input"
            />
            <span class="form-hint">{{ cfg.description }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
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

.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
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

.btn-secondary {
  background: var(--bg-hover);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-active);
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

/* ============================================================
   抽屉布局
   ============================================================ */

.drawers {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--border-color);
}

.drawer {
  background: var(--bg-sidebar);
}

.drawer-header {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px 20px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-primary);
  transition: background 0.15s;
}

.drawer-header:hover {
  background: var(--bg-hover);
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.drawer-title h2 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.drawer-chevron {
  font-size: 10px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
  display: inline-block;
  width: 14px;
}

.drawer.open .drawer-chevron {
  transform: rotate(90deg);
}

.drawer-badge {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-active);
  padding: 1px 8px;
  border-radius: 10px;
}

.drawer-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  padding-left: 24px;
}

.drawer-body {
  display: none;
  padding: 0 20px 20px;
}

.drawer.open .drawer-body {
  display: block;
}

.form-row {
  margin-top: 14px;
}

.form-row label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-family: monospace;
}

.form-input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  font-family: monospace;
  transition: border-color 0.15s;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.form-select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s;
  appearance: auto;
}

.form-select:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(78, 110, 242, 0.15);
}

.form-hint {
  display: block;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 3px;
}

.restart-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 500;
  color: #d97706;
  background: #fef3c7;
  padding: 0 5px;
  border-radius: 3px;
  margin-left: 4px;
  font-family: inherit;
}

[data-theme="dark"] .restart-badge {
  color: #fbbf24;
  background: #78350f;
}
</style>