<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

    <div v-else class="config-sections">
      <!-- 默认模型 -->
      <section class="config-section">
        <h2>默认模型</h2>
        <div v-for="cfg in configs.filter(c => llmConfigKeys.has(c.key))" :key="cfg.key" class="form-group">
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
      </section>

      <!-- 深度思考模型 -->
      <section class="config-section">
        <h2>深度思考模型</h2>
        <p class="section-desc">深度思考模式使用独立的模型配置，可与默认模型完全不同</p>
        <div v-for="cfg in configs.filter(c => c.key.startsWith('deep_'))" :key="cfg.key" class="form-group">
          <label :for="cfg.key">
            {{ cfg.key }}
            <span v-if="cfg.restart_required" class="restart-badge">⚠️ 需重启</span>
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
      </section>

      <!-- 系统配置 -->
      <section v-if="configs.some(c => systemConfigKeys.has(c.key))" class="config-section">
        <h2>系统配置</h2>
        <p class="section-desc">通用系统设置（带 ⚠️ 标记的项需重启服务后生效）</p>
        <div v-for="cfg in configs.filter(c => systemConfigKeys.has(c.key))" :key="cfg.key" class="form-group">
          <label :for="cfg.key">
            {{ cfg.key }}
            <span v-if="cfg.restart_required" class="restart-badge">⚠️ 需重启</span>
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
      </section>
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

.config-sections {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.config-section {
  background: var(--bg-sidebar);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 24px;
}

.config-section h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.section-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 20px;
}

.form-group {
  margin-top: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-family: monospace;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
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
  padding: 8px 12px;
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
  margin-top: 4px;
}

.restart-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  color: #d97706;
  background: #fef3c7;
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: 6px;
  font-family: inherit;
}

[data-theme="dark"] .restart-badge {
  color: #fbbf24;
  background: #78350f;
}
</style>