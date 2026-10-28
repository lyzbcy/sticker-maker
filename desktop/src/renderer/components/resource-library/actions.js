import { watch } from 'vue'
import { emptyStatus } from './state'
import { transferOutcomePrefix, transferOutcomeStateText, transferOutcomeClass, resultCount, importedCount } from './presenters'
export function createLibraryActions(state, gateway, scheduleRefresh) {
const { library, errorMessage, accountInput, confirmLegacy, accountTip, binding, exportMode, exportTarget, cleanupOld, previewing, executing, plan, sourcePath, connecting, importing, importTip, workInput, handingOff, handoffMessage, executionResult, progressInfo, progressStage, elapsedSeconds, transferTipClass, refreshing, mounted, counts, offline, warnings, settingsConflicts, tasks, conflicts, unresolvedOperations, deletedWorks, hiddenWorks, missing, entryCount, canExecutePlan, executeDisabledReason, transferBusy, conflictBlockCount, resolvingRevision, resolveMessage, reconcilingOperation, recordAction } = state
const { api, send, responseError, exceptionError } = gateway
let pollInFlight = false
let statusReadError = null
// A recovered poll clears only its own read error, never a later operation error.
watch(errorMessage, () => { statusReadError = null }, { flush: 'sync' })
function setStatusReadError(message) { errorMessage.value = message; statusReadError = message }
function setError(res, fallback) { statusReadError = null; errorMessage.value = responseError(res, fallback) }
function acceptStatus(data) {
  if (data && typeof data === 'object') library.value = { ...emptyStatus(), ...data, counts: { ...emptyStatus().counts, ...(data.counts || {}) } }
}

async function refreshStatus(options = {}) {
  if (!mounted.value) return null
  if (pollInFlight) return null
  pollInFlight = true
  if (!options.quiet) refreshing.value = true
  try {
    const res = await send('library_status', {})
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      if (!options.quiet || (statusReadError !== null && errorMessage.value === statusReadError)) errorMessage.value = ''
      statusReadError = null
      return res.data
    }
    if (!options.quiet) setStatusReadError(responseError(res, '读取资源库状态失败'))
  } catch (err) {
    if (!options.quiet) setStatusReadError(exceptionError(err, '读取资源库状态失败'))
  } finally {
    pollInFlight = false
    if (!options.quiet) refreshing.value = false
  }
  return null
}

async function refreshLibrary() {
  if (refreshing.value || pollInFlight) return
  pollInFlight = true
  refreshing.value = true
  try {
    const res = await send('library_refresh', {})
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      errorMessage.value = ''
    } else setError(res, '刷新资源库失败')
  } catch (err) { errorMessage.value = exceptionError(err, '刷新资源库失败') }
  finally { refreshing.value = false; pollInFlight = false }
}

function normalizePathResult(result) {
  if (typeof result === 'string') return result
  if (result && !result.canceled) return result.path || ''
  return ''
}
async function chooseExportTarget() {
  if (!api()?.selectDirectory) return
  try {
    const selected = normalizePathResult(await api().selectDirectory())
    if (!selected || selected === exportTarget.value) return
    exportTarget.value = selected
    invalidatePlan()
  } catch (err) { errorMessage.value = exceptionError(err, '选择导出位置失败') }
}
async function chooseSourcePath() {
  if (!api()?.selectDirectory) return
  try {
    const selected = normalizePathResult(await api().selectDirectory())
    if (selected) sourcePath.value = selected
  } catch (err) { errorMessage.value = exceptionError(err, '选择资源库位置失败') }
}

async function bindAccount() {
  if (!accountInput.value || !confirmLegacy.value || binding.value) return
  binding.value = true
  accountTip.value = ''
  try {
    const res = await send('library_bind_account', { account: accountInput.value, confirm_legacy: true })
    if (res?.status === 'ok') {
      accountTip.value = '✓ 已绑定账号；旧作品会按资源库身份合并'
      await refreshStatus({ quiet: true })
    } else setError(res, '账号绑定失败')
  } catch (err) { errorMessage.value = exceptionError(err, '账号绑定失败') }
  finally { binding.value = false }
}

async function previewExport() {
  if (!exportTarget.value || previewing.value) return
  previewing.value = true
  plan.value = null
  executionResult.value = null
  try {
    const res = await send('library_preview', {
      target: exportTarget.value,
      mode: exportMode.value,
      cleanup: exportMode.value === 'migration' && cleanupOld.value,
    })
    if (res?.status === 'ok' && res.data) plan.value = res.data
    else setError(res, '生成导出预览失败')
  } catch (err) { errorMessage.value = exceptionError(err, '生成导出预览失败') }
  finally { previewing.value = false }
}

function invalidatePlan() {
  plan.value = null
  executionResult.value = null
  importTip.value = ''
}

watch(exportMode, (mode) => {
  if (mode !== 'migration') cleanupOld.value = false
  invalidatePlan()
})
watch(cleanupOld, invalidatePlan)

async function executeExport() {
  if (!canExecutePlan.value || executing.value) return
  executing.value = true
  try {
    const res = await send('library_execute', { plan_id: plan.value.plan_id })
    if (res?.status === 'ok') {
      executionResult.value = res.data || {}
      setTransferTip(`${transferOutcomePrefix(res.data?.state)} ${transferOutcomeStateText(res.data?.state)}：已复制 ${resultCount(res.data?.copied)} 项`, res.data?.state)
      await refreshStatus({ quiet: true })
    } else setError(res, '执行导出失败')
  } catch (err) { errorMessage.value = exceptionError(err, '执行导出失败') }
  finally { executing.value = false }
}
async function resumeTask(task) {
  const planId = task?.plan_id || task?.id
  if (!planId || executing.value) return
  executing.value = true
  try {
    const res = await send('library_execute', { plan_id: planId })
    if (res?.status === 'ok') {
      executionResult.value = res.data || {}
      setTransferTip(`${transferOutcomePrefix(res.data?.state)} 任务 ${planId} ${transferOutcomeStateText(res.data?.state)}（已复制 ${resultCount(res.data?.copied)} 项）`, res.data?.state)
      await refreshStatus({ quiet: true })
    } else setError(res, '恢复任务失败')
  } catch (err) { errorMessage.value = exceptionError(err, '恢复任务失败') }
  finally { executing.value = false }
}
async function connectLibrary() {
  if (!sourcePath.value || connecting.value) return
  connecting.value = true
  try {
    const res = await send('library_connect', { path: sourcePath.value })
    if (res?.status === 'ok') { acceptStatus(res.data); setTransferTip('✓ 已连接共享资源库') }
    else setError(res, '连接共享资源库失败')
  } catch (err) { errorMessage.value = exceptionError(err, '连接共享资源库失败') }
  finally { connecting.value = false }
}
async function importLibrary() {
  if (!sourcePath.value || importing.value) return
  importing.value = true
  try {
    const res = await send('library_import', { path: sourcePath.value })
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      setTransferTip(`✓ 已导入 ${importedCount(res.data?.imported)} 项`)
    }
    else setError(res, '复制导入失败')
  } catch (err) { errorMessage.value = exceptionError(err, '复制导入失败') }
  finally { importing.value = false }
}
async function openLibrary() {
  if (library.value.root && api()?.send) await send('open_in_finder', { path: library.value.root })
}
async function resolveConflict(conflict, head, action) {
  const revisionId = head?.revision_id
  if (!conflict?.work_id || !revisionId || resolvingRevision.value) return
  resolvingRevision.value = revisionId
  resolveMessage.value = ''
  try {
    const res = await send('library_resolve', { work_id: conflict.work_id, revision_id: revisionId, action })
    if (res?.status === 'ok') {
      resolveMessage.value = `✓ 已选用版本 ${String(revisionId).slice(0, 8)}，正在刷新资源库状态（可能需要十几秒）…`
      await refreshStatus({ quiet: true })
      // 竞态兜底：resolve 返回时若 8 秒轮询正在跑，上面的刷新会被跳过，
      // 稍后强制再拉一次，确保冲突卡片真正消失
      scheduleRefresh(1500)
    } else {
      setError(res, '处理版本冲突失败')
      resolveMessage.value = `✗ ${responseError(res, '处理版本冲突失败')}`
    }
  } catch (err) {
    errorMessage.value = exceptionError(err, '处理版本冲突失败')
    resolveMessage.value = `✗ ${exceptionError(err, '处理版本冲突失败')}`
  } finally { resolvingRevision.value = '' }
}
async function reconcileOperation(operation, outcome) {
  const operationId = operation?.operation_id
  if (!operationId || reconcilingOperation.value) return
  reconcilingOperation.value = operationId
  try {
    const res = await send('library_reconcile', { operation_id: operationId, outcome })
    if (res?.status === 'ok') await refreshStatus({ quiet: true })
    else setError(res, '提交结果核对失败')
  } catch (err) { errorMessage.value = exceptionError(err, '提交结果核对失败') }
  finally { reconcilingOperation.value = '' }
}
async function deleteWork(action) {
  if (!workInput.value || recordAction.value) return
  if (action === 'delete' && typeof window !== 'undefined' && !window.confirm('共享删除会创建可同步的删除版本，确认继续吗？')) return
  recordAction.value = action
  try {
    const res = await send('library_delete', { work_id: workInput.value, action })
    if (res?.status === 'ok') {
      setTransferTip(action === 'restore' ? '✓ 已请求恢复作品' : action === 'hide' ? '✓ 已在本机隐藏作品' : '✓ 已创建共享删除版本')
      await refreshStatus({ quiet: true })
    }
    else setError(res, '处理作品记录失败')
  } catch (err) { errorMessage.value = exceptionError(err, '处理作品记录失败') }
  finally { recordAction.value = '' }
}
async function unhideWork(work) {
  const workId = work?.work_id
  if (!workId || recordAction.value) return
  recordAction.value = 'unhide'
  try {
    const res = await send('library_delete', { work_id: workId, action: 'unhide' })
    if (res?.status === 'ok') {
      setTransferTip('✓ 已取消本机隐藏')
      await refreshStatus({ quiet: true })
    } else setError(res, '取消本机隐藏失败')
  } catch (err) { errorMessage.value = exceptionError(err, '取消本机隐藏失败') }
  finally { recordAction.value = '' }
}
async function handoff() {
  if (handingOff.value) return
  handingOff.value = true
  handoffMessage.value = ''
  try {
    const res = await send('library_handoff', {})
    if (res?.status === 'ok') handoffMessage.value = res.data?.message || '已保存到共享目录，请等待 Syncthing 完成同步。'
    else setError(res, '准备切换电脑失败')
  } catch (err) { errorMessage.value = exceptionError(err, '准备切换电脑失败') }
  finally { handingOff.value = false }
}
function setTransferTip(message, state = 'completed') {
  importTip.value = message
  transferTipClass.value = transferOutcomeClass(state)
}

return { setError, acceptStatus, refreshStatus, refreshLibrary, normalizePathResult, chooseExportTarget, chooseSourcePath, bindAccount, previewExport, invalidatePlan, executeExport, resumeTask, connectLibrary, importLibrary, openLibrary, resolveConflict, reconcileOperation, deleteWork, unhideWork, handoff, isPolling: () => pollInFlight }
}
