import { computed, watch } from 'vue'
export function createLibraryProgress(state) {
const { previewing, executing, transferBusy, progressInfo, progressStage, mounted, elapsedSeconds } = state
let elapsedTimer = null
const progressPercent = computed(() => {
  if (previewing.value) return null
  const n = Number(progressInfo.value?.percent)
  return Number.isFinite(n) && n >= 0 ? Math.min(100, Math.round(n)) : null
})
const progressText = computed(() => {
  if (previewing.value) {
    const info = progressInfo.value
    if (info?.phase === 'scan' && Number.isFinite(info.scanned)) {
      return info.done
        ? `扫描完成：共检查 ${info.scanned} 个文件，正在汇总清单…`
        : `正在扫描资源库并校验文件哈希：已检查 ${info.scanned} 个文件…`
    }
    return progressStage.value || '正在扫描资源库并校验文件清单，文件多时可能需要几分钟…'
  }
  const info = progressInfo.value
  if (!info) return '正在校验清单并准备复制…'
  const label = info.phase === 'cleanup' ? '清理旧位置文件' : '复制到目标位置'
  return `${label}：${info.completed} / ${info.total} 项（${info.percent}%）`
})
function acceptProgress(ev) {
  if (!mounted.value || ev?.stage !== 'library' || !transferBusy.value) return
  if (previewing.value && typeof ev.message === 'string' && !ev.scanned) {
    progressStage.value = ev.message
  }
  let completed = Number(ev.completed)
  let total = Number(ev.total)
  let phase = ev.phase
  // 旧引擎把进度 dict 拍平成 message 字符串，从中兜底解析计数
  if (!(Number.isFinite(completed) && Number.isFinite(total) && total > 0)) {
    const match = typeof ev.message === 'string'
      ? ev.message.match(/'completed':\s*(\d+),?\s*'total':\s*(\d+)/) : null
    if (match) { completed = Number(match[1]); total = Number(match[2]) }
  }
  if (!phase && typeof ev.message === 'string') {
    if (ev.message.includes("'phase': 'cleanup'")) phase = 'cleanup'
    else if (ev.message.includes("'phase': 'scan'")) phase = 'scan'
  }
  if (Number.isFinite(completed) && Number.isFinite(total) && total > 0) {
    progressInfo.value = {
      phase: phase || 'copy',
      completed,
      total,
      percent: Math.min(100, Math.round((completed / total) * 100)),
    }
    return
  }
  const scanned = Number(ev.scanned)
  if (Number.isFinite(scanned)) {
    progressInfo.value = { phase: phase || 'scan', scanned, done: Boolean(ev.done) }
  }
}
watch(transferBusy, (busy) => {
  if (busy) {
    elapsedSeconds.value = 0
    progressInfo.value = null
    progressStage.value = ''
    if (!elapsedTimer) elapsedTimer = setInterval(() => { if (mounted.value) elapsedSeconds.value += 1 }, 1000)
  } else if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
})


function stop() { if (elapsedTimer) clearInterval(elapsedTimer); elapsedTimer = null }
return { acceptProgress, progressPercent, progressText, stop }
}
