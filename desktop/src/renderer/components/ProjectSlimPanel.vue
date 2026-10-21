<template>
  <section v-if="mode" class="project-slim" data-test="project-slim">
    <h3>工程瘦身 · {{ mode === 'delivery' ? '精简工程' : '完整工程' }}</h3>
    <p v-if="mode === 'delivery'">已删除源图。可查看、导出、评分及使用现有素材投稿；重新裁切、加字和生成素材需导入完整工程。</p>
    <p v-else>默认只清理可重建缓存，最终表情、投稿素材、人工评分与工程身份保持。</p>
    <p class="scope-note">仅清理当前工程；旧资源库和备份需单独处理。</p>
    <label v-if="mode !== 'delivery'"><input v-model="deleteSources" data-test="delete-sources" type="checkbox" :disabled="busy" />
      删除原图和参考图，转为精简工程（无法恢复源图编辑能力）</label>
    <div>
      <button data-test="slim-preview" :disabled="busy || !canEdit" @click="preview">预览瘦身</button>
      <template v-if="plan">
        <p>本次将释放 {{ size(plan.bytes) }}。{{ plan.delete_sources ? '将永久删除本次清单内的原图和参考图。' : '只清理缓存。' }}</p>
        <label v-if="plan.delete_sources"><input v-model="confirmed" data-test="confirm-source-removal" type="checkbox" />我确认删除原图，保留成品和投稿资料</label>
        <button data-test="slim-execute" :disabled="busy || (plan.delete_sources && !confirmed)" @click="execute">执行此预览</button>
      </template>
    </div>
    <button v-if="cleanupPending" data-test="cleanup-resume" :disabled="busy" @click="resume">继续上次中断的清理</button>
    <p v-if="busy" role="status">正在校验工程文件…</p>
    <p v-if="message" role="status">{{ message }}</p><p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { storageSize as size } from '../utils/storageSize'
const props = defineProps({ path: String, mode: String, canEdit: Boolean, cleanupPending: Boolean })
const emit = defineEmits(['changed'])
const deleteSources = ref(false), confirmed = ref(false), plan = ref(null), busy = ref(false), message = ref(''), error = ref('')
watch([deleteSources, () => props.path], () => { plan.value = null; confirmed.value = false; message.value = '' })
async function request(cmd, args) {
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await window.api.send(cmd, args)
    if (result?.status !== 'ok') throw new Error(result?.errors?.[0]?.message || '瘦身失败')
    return result.data
  } catch (e) { error.value = e.message; return null }
  finally { busy.value = false }
}
async function preview() {
  confirmed.value = false
  plan.value = await request('project_slim_preview', { paths: [props.path], delete_sources: props.mode !== 'delivery' && deleteSources.value })
}
async function execute() {
  if (!plan.value || (plan.value.delete_sources && !confirmed.value)) return
  const data = await request('project_slim_execute', { plan_id: plan.value.plan_id, confirm_discard_sources: confirmed.value })
  if (data) { message.value = `已释放 ${size(data.freed_bytes)}`; plan.value = null; emit('changed') }
}
async function resume() {
  if (await request('project_cleanup_resume', { episode_dir: props.path })) emit('changed')
}
</script>

<style scoped>
.project-slim { padding: 22px 24px; border: 1.5px solid var(--paper); border-radius: var(--r-card); background: var(--card); box-shadow: var(--shadow-card); }
h3 { margin: 0 0 14px; padding-bottom: 10px; border-bottom: 1.5px dashed var(--paper); font: 700 15px var(--font-head); color: var(--forest); }
p, label { line-height: 1.65; font-size: 13px; } label { display: block; }
button { margin: 12px 8px 0 0; padding: 9px 16px; border: 1.5px solid var(--forest); border-radius: var(--r-pill); background: var(--card); color: var(--forest); font: 600 12.5px var(--font-body); cursor: pointer; }
button:hover:not(:disabled) { background: var(--forest); color: var(--white); }
button:disabled { opacity: .45; cursor: not-allowed; } input { accent-color: var(--forest); } [role=alert] { color: var(--brick); }
</style>
