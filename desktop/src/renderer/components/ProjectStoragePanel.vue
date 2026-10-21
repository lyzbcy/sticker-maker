<template>
  <section class="project-storage" data-test="project-storage">
    <h4>{{ direct ? '规范工程 · 单份存储' : '转换为规范工程' }}</h4>
    <p>每弹直接使用专辑名文件夹，例如「周三涵做表情37」「星星布丁第一弹」。工程就是工作目录，无需完整缓存副本。</p>
    <template v-if="!direct">
      <p>请先暂停其他电脑对旧库的制作和修改，再预览并转换。旧库和工作副本暂保留，不会在转换时删除原图。</p>
      <button class="btn secondary" data-test="project-target" :disabled="busy" @click="choose">选择工程根目录…</button>
      <p>{{ target || '尚未选择' }}</p>
      <button class="btn primary" data-test="project-preview" :disabled="busy || !target" @click="preview">生成转换预览</button>
      <div v-if="plan" data-test="project-plan">
        <p>{{ plan.entries?.length || 0 }} 个工程 · {{ size(plan.bytes) }} · {{ plan.missing?.length || 0 }} 项待处理</p>
        <p v-for="(item,i) in (plan.missing || []).slice(0,12)" :key="i">{{ item.path || item.work_id }}：{{ item.reason }}</p>
        <button class="btn primary" data-test="project-execute" :disabled="busy || !!plan.missing?.length" @click="execute">按预览转换并使用工程目录</button>
      </div>
    </template>
    <template v-else>
      <p>本机工作副本已停用。完整工程保留源图；精简工程保留最终表情、投稿素材、人工评分及工程清单。可在作品详情中预览瘦身。</p>
      <button data-test="normalize-preview" :disabled="busy" @click="previewNormalize">预览规范现有专辑目录</button>
      <div v-if="normalizePlan">
        <p>识别 {{ normalizePlan.entries?.length || 0 }} 个旧目录，包括「星星布丁第N弹」。保留文件夹名称，将散放的成品图片移入「最终版」，添加工程清单。</p>
        <p v-for="(item,i) in normalizePlan.missing || []" :key="i">{{ item.path }}：{{ item.reason }}</p>
        <button data-test="normalize-execute" :disabled="busy || !!normalizePlan.missing?.length" @click="executeNormalize">按预览规范目录</button>
      </div>
      <template v-if="migrationId && !retired">
        <button data-test="old-copies-preview" :disabled="busy" @click="previewOldCopies">预览释放旧库和工作副本</button>
        <div v-if="cleanupPlan">
          <p>预计净释放 {{ size(cleanupPlan.estimated_freed_bytes) }}；独有历史文件 {{ size(cleanupPlan.history_bytes) }} 会保留到工程集合的历史档案。</p>
          <p>清理删除会随 Syncthing 传播。其他电脑需改用此工程目录，再执行清理。</p>
          <label><input v-model="cleanupConfirmed" data-test="old-copies-confirm" type="checkbox" />已确认新工程可用，其他电脑已切换或停止使用旧库</label>
          <button data-test="old-copies-execute" :disabled="busy || !cleanupConfirmed" @click="cleanupOldCopies">按预览释放旧副本</button>
        </div>
      </template>
    </template>
    <button class="btn secondary" data-test="project-connect" :disabled="busy" @click="connect">连接已有规范工程目录…</button>
    <p v-if="busy" role="status">{{ progress || '正在校验工程，请稍候…' }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert" class="project-error">{{ error }}</p>
  </section>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { storageSize as size } from '../utils/storageSize'
const props = defineProps({ direct: Boolean, migrationId: String, retired: Boolean })
const emit = defineEmits(['changed'])
const target = ref(''), plan = ref(null), busy = ref(false), error = ref(''), message = ref(''), progress = ref('')
const cleanupPlan = ref(null), cleanupConfirmed = ref(false)
const normalizePlan = ref(null)
watch(target, () => { plan.value = null })
async function choose() {
  const value = await window.api?.selectDirectory()
  const path = typeof value === 'string' ? value : value?.path || value?.filePaths?.[0]
  if (path) target.value = path
  return path || null
}
async function request(cmd, args) {
  busy.value = true; error.value = ''; message.value = ''; progress.value = ''
  try {
    const res = await window.api.send(cmd, args)
    if (res?.status !== 'ok') throw new Error(res?.errors?.[0]?.message || '工程操作失败')
    return res.data
  } catch (e) { error.value = e.message; return null }
  finally { busy.value = false }
}
async function preview() { plan.value = await request('project_migration_preview', { target: target.value }) }
async function execute() {
  if (!plan.value || plan.value.missing?.length) return
  const res = await request('project_migration_execute', { plan_id: plan.value.plan_id })
  if (res) { message.value = res.message; plan.value = null; emit('changed') }
}
async function previewOldCopies() {
  cleanupConfirmed.value = false
  cleanupPlan.value = await request('project_old_copies_preview', { migration_id: props.migrationId })
}
async function previewNormalize() { normalizePlan.value = await request('project_normalize_preview', {}) }
async function executeNormalize() {
  if (!normalizePlan.value || normalizePlan.value.missing?.length) return
  const result = await request('project_normalize_execute', { plan_id: normalizePlan.value.plan_id })
  if (result) { message.value = `已规范 ${result.normalized} 个旧目录`; normalizePlan.value = null; emit('changed') }
}
async function cleanupOldCopies() {
  if (!cleanupPlan.value || !cleanupConfirmed.value) return
  const result = await request('project_old_copies_execute', { plan_id: cleanupPlan.value.plan_id })
  if (result) {
    message.value = result.errors?.length ? `部分文件保留：${result.errors.length} 项，重新预览后可继续` : `旧副本清理完成，已处理 ${size(result.cleaned_bytes)}`
    cleanupPlan.value = null; emit('changed')
  }
}
async function connect() {
  const chosen = await choose()
  if (!chosen) return
  const res = await request('project_connect', { path: chosen })
  if (res) { message.value = '已连接规范工程目录'; emit('changed') }
}
let unsubscribe
onMounted(() => {
  unsubscribe = window.api?.onProgress?.(event => {
    if (busy.value && event?.stage === 'library') progress.value = event.message || ''
  })
})
onBeforeUnmount(() => { if (typeof unsubscribe === 'function') unsubscribe() })
</script>

<style scoped>
.project-storage { padding: 20px; margin: 16px 0; border: 1.5px solid var(--paper); border-radius: var(--r-card); background: var(--card); box-shadow: var(--shadow-card); }
h4 { margin: 0 0 12px; font: 700 16px var(--font-head); color: var(--forest); }
p, label { line-height: 1.65; overflow-wrap: anywhere; font-size: 13px; }
button { margin: 4px 8px 4px 0; padding: 9px 16px; border: 1.5px solid var(--forest); border-radius: var(--r-pill); background: var(--forest); color: var(--white); font: 600 12.5px var(--font-body); cursor: pointer; }
button.secondary { background: var(--card); color: var(--forest); }
button:hover:not(:disabled) { background: var(--forest-hover); color: var(--white); }
button:disabled { cursor: not-allowed; opacity: .45; } input { accent-color: var(--forest); }
.project-error { color: var(--brick); }
</style>
