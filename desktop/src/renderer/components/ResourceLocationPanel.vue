<template>
  <section v-if="!compact || (loaded && (!status.connected || status.offline))" class="location-card" data-test="resource-location">
    <div class="location-heading">
      <div><h3>{{ status.offline ? '资源位置暂不可用' : status.connected ? '资源位置' : '选择已有表情资源' }}</h3>
        <p>{{ status.connected ? status.root : '换电脑后，选择原来的共享文件夹即可找回作品和评分。' }}</p></div>
      <button data-test="choose-resource-location" :disabled="busy" @click="choose">{{ busy ? '正在校验…' : '选择资源位置…' }}</button>
    </div>
    <p class="location-hint">可选择资源库、规范工程集合，或它们的上层文件夹。连接后会记住位置，下次自动加载。</p>
    <div v-if="candidates.length" class="location-form">
      <label>识别到的资源<select v-model="selectedPath" data-test="location-candidate" :disabled="busy">
        <option v-for="item in candidates" :key="item.path" :value="item.path">{{ item.storage_mode === 'projects' ? '规范工程' : '旧资源库' }} · {{ item.path }}</option>
      </select></label>
      <label>资源所属账号<select v-model="accountId" data-test="location-account" :disabled="busy">
        <option value="" disabled>请选择账号</option>
        <option v-for="account in selected?.accounts || []" :key="account.account_id" :value="account.account_id">{{ account.account_label }}</option>
      </select></label>
      <p v-if="!selected?.accounts?.length">尚未发现完整账号记录，请确认文件已经同步到本机。</p>
      <p v-if="selected?.storage_mode === 'legacy'" class="location-hint">这是旧资源库，连接时仍会建立工作副本；连接后可在「账号与资源库」转换为规范工程，停用工作副本。</p>
      <p v-else class="location-hint">直接读取工程文件夹，不建立完整工作副本。</p>
      <label class="location-confirm"><input v-model="confirmed" data-test="location-confirm" type="checkbox" :disabled="busy" />我确认这些资源属于所选账号，并使用此资源位置</label>
      <button data-test="connect-resource-location" :disabled="busy || !accountId || !confirmed" @click="connect">连接并记住位置</button>
    </div>
    <p v-if="busy" role="status">正在读取资源清单，文件较多时请稍候…</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert" class="location-error">{{ error }}</p>
  </section>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useEngineStore } from '../store/engine'
const props = defineProps({ compact: Boolean, initialStatus: Object })
const emit = defineEmits(['changed'])
const store = useEngineStore()
const status = ref({}), loaded = ref(false), busy = ref(false), error = ref(''), message = ref('')
const candidates = ref([]), selectedPath = ref(''), accountId = ref(''), confirmed = ref(false)
const selected = computed(() => candidates.value.find(item => item.path === selectedPath.value))
watch(() => props.initialStatus, value => { if (value) { status.value = value; loaded.value = true } }, { immediate: true })
watch(selectedPath, () => { accountId.value = selected.value?.accounts?.length === 1 ? selected.value.accounts[0].account_id : ''; confirmed.value = false })
watch(accountId, () => { confirmed.value = false })
async function request(cmd, args = {}) {
  const res = await window.api.send(cmd, args)
  if (res?.status !== 'ok') throw new Error(res?.errors?.[0]?.message || '资源操作失败')
  return res.data || {}
}
onMounted(async () => {
  if (props.initialStatus || !window.api?.send) return
  try { status.value = await request('library_status') }
  catch (e) { error.value = e.message }
  finally { loaded.value = true }
})
async function choose() {
  if (busy.value || !window.api?.selectDirectory) return
  error.value = ''; message.value = ''
  try {
    const result = await window.api.selectDirectory()
    const path = typeof result === 'string' ? result : !result?.canceled && (result?.path || result?.filePaths?.[0])
    candidates.value = []; selectedPath.value = ''; accountId.value = ''; confirmed.value = false
    if (!path) return
    busy.value = true
    const data = await request('project_location_inspect', { path })
    candidates.value = data.candidates || []
    selectedPath.value = candidates.value[0]?.path || ''
    if (data.errors?.length) error.value = data.errors.map(item => `${item.path}：${item.message}`).join('；')
    if (!candidates.value.length && !error.value) error.value = '没有识别到资源库或规范工程，请选择包含 library.json 或 projects.json 的目录，或它的上层目录。'
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function connect() {
  if (busy.value || !confirmed.value || !selected.value || !accountId.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    status.value = await request('project_location_connect', { path: selected.value.path, library_id: selected.value.library_id,
      account_id: accountId.value, confirm_account: true })
    candidates.value = []; selectedPath.value = ''; confirmed.value = false
    message.value = '已连接，资源位置已保存，下次启动自动加载。'
    const prefs = await request('load_prefs')
    if (prefs.prefs) store.prefs = prefs.prefs
    await Promise.all([store.loadCharacters(), store.loadSeries()])
    emit('changed', status.value)
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>
<style scoped>
.location-card { margin: 18px 0; padding: 20px; border: 1.5px solid var(--line); border-radius: 18px; background: var(--card); min-width: 0; }
.location-heading { display: flex; gap: 16px; justify-content: space-between; align-items: center; flex-wrap: wrap; }
h3 { margin: 0 0 8px; font-size: 17px; } p { margin: 8px 0; overflow-wrap: anywhere; }
.location-hint { color: var(--muted); font-size: 13px; line-height: 1.6; }
.location-form { display: grid; gap: 12px; margin-top: 16px; }
label { display: grid; gap: 6px; font-size: 14px; }
select { padding: 9px; width: 100%; min-width: 0; border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--ink); }
.location-confirm { display: flex; align-items: center; gap: 8px; }
button { justify-self: start; padding: 10px 16px; border: 0; border-radius: 12px; background: var(--forest); color: white; cursor: pointer; font: inherit; }
button:disabled { opacity: .5; cursor: default; } .location-error { color: var(--brick); }
</style>
