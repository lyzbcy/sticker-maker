import { computed, ref } from 'vue'
export const emptyStatus = () => ({
  connected: false, offline: false, root: '', library_id: '', account_id: '', account_label: '', accounts: [],
  workspace_path: '',
  counts: { available: 0, placeholder: 0, pending: 0, conflict: 0, deleted: 0 }, tasks: [], conflicts: [],
  warnings: [], settings_conflicts: [], hidden: [],
  unresolved_operations: [],
})

export function createLibraryState() {


const library = ref(emptyStatus())
const errorMessage = ref('')
const accountInput = ref('')
const confirmLegacy = ref(false)
const accountTip = ref('')
const binding = ref(false)
const exportMode = ref('backup')
const exportTarget = ref('')
const cleanupOld = ref(false)
const previewing = ref(false)
const executing = ref(false)
const plan = ref(null)
const sourcePath = ref('')
const connecting = ref(false)
const importing = ref(false)
const importTip = ref('')
const workInput = ref('')
const handingOff = ref(false)
const handoffMessage = ref('')
const executionResult = ref(null)
const progressInfo = ref(null)
const progressStage = ref('')
const elapsedSeconds = ref(0)
const transferTipClass = ref('transfer-success')
const refreshing = ref(false)
const mounted = ref(false)

const counts = computed(() => ({
  available: Number(library.value.counts?.available || 0),
  placeholder: Number(library.value.counts?.placeholder || 0),
  pending: Number(library.value.counts?.pending || 0),
  conflict: Number(library.value.counts?.conflict || 0),
  deleted: Number(library.value.counts?.deleted || 0),
}))
const offline = computed(() => !!library.value.offline)
const warnings = computed(() => Array.isArray(library.value.warnings) ? library.value.warnings : [])
const settingsConflicts = computed(() => Array.isArray(library.value.settings_conflicts)
  ? library.value.settings_conflicts : [])
const tasks = computed(() => (Array.isArray(library.value.tasks) ? library.value.tasks : [])
  .filter(task => task?.state !== 'completed'))
const conflicts = computed(() => Array.isArray(library.value.conflicts) ? library.value.conflicts : [])
const unresolvedOperations = computed(() => Array.isArray(library.value.unresolved_operations)
  ? library.value.unresolved_operations : [])
const deletedWorks = computed(() => {
  if (Array.isArray(library.value.deleted_works)) return library.value.deleted_works
  if (Array.isArray(library.value.deleted)) return library.value.deleted
  return (Array.isArray(library.value.works) ? library.value.works : [])
    .filter(item => item.resource_state === 'deleted' || item.deleted)
})
const hiddenWorks = computed(() => {
  if (Array.isArray(library.value.hidden_works)) return library.value.hidden_works
  if (Array.isArray(library.value.hidden)) return library.value.hidden
  return []
})
const missing = computed(() => Array.isArray(plan.value?.missing) ? plan.value.missing : [])
const entryCount = computed(() => {
  if (Array.isArray(plan.value?.entries)) return plan.value.entries.length
  if (plan.value?.entries && typeof plan.value.entries === 'object') return Object.keys(plan.value.entries).length
  return 0
})
const canExecutePlan = computed(() => {
  const cleanup = exportMode.value === 'migration' && cleanupOld.value
  return !!plan.value?.plan_id && missing.value.length === 0 &&
    plan.value.mode === exportMode.value && Boolean(plan.value.cleanup) === cleanup
})
const executeDisabledReason = computed(() => {
  if (executing.value) return ''
  if (!plan.value?.plan_id) return '请先生成预览'
  if (missing.value.length) return `清单仍缺失 ${missing.value.length} 项，补齐后重新预览`
  const cleanup = exportMode.value === 'migration' && cleanupOld.value
  if (plan.value.mode !== exportMode.value) return '预览与当前导出用途不一致，请重新预览'
  if (Boolean(plan.value.cleanup) !== cleanup) return '清理开关与预览时不一致，请重新预览'
  return ''
})
const transferBusy = computed(() => previewing.value || executing.value)
const conflictBlockCount = computed(() => conflicts.value.length + settingsConflicts.value.length)

const resolvingRevision = ref('')
const resolveMessage = ref('')
const reconcilingOperation = ref('')
const recordAction = ref('')

return { library, errorMessage, accountInput, confirmLegacy, accountTip, binding, exportMode, exportTarget, cleanupOld, previewing, executing, plan, sourcePath, connecting, importing, importTip, workInput, handingOff, handoffMessage, executionResult, progressInfo, progressStage, elapsedSeconds, transferTipClass, refreshing, mounted, counts, offline, warnings, settingsConflicts, tasks, conflicts, unresolvedOperations, deletedWorks, hiddenWorks, missing, entryCount, canExecutePlan, executeDisabledReason, transferBusy, conflictBlockCount, resolvingRevision, resolveMessage, reconcilingOperation, recordAction }
}
