export function missingLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.logical_path || item?.source_path || item?.path || item?.name || JSON.stringify(item)
}
export function warningLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.message || item?.detail || item?.warning || item?.path || JSON.stringify(item)
}
export function conflictLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.message || item?.detail || item?.setting_type || item?.name || JSON.stringify(item)
}
// 设置冲突各版本的内容摘要：帮助用户分辨两台设备改了什么
export function conflictDetail(item) {
  if (typeof item === 'string') return item
  return item?.message || item?.detail || ''
}
export function settingsHeadSummary(head) {
  const payload = head?.metadata?.payload || {}
  const bits = []
  if (payload.sticker_price != null) bits.push(`价格 ${payload.sticker_price}`)
  if (payload.grid_size != null) bits.push(`宫格 ${payload.grid_size}`)
  if (payload.story_mode != null) bits.push(payload.story_mode ? '剧情模式' : '普通模式')
  if (payload.default_series_id) bits.push(`默认系列 ${String(payload.default_series_id).slice(0, 8)}`)
  if (payload.reference_lib_path) bits.push(`参考图库 ${payload.reference_lib_path}`)
  if (payload.transparent_default != null) bits.push(payload.transparent_default ? '默认透明底' : '默认白底')
  return bits.length ? bits.join(' · ') : '（无差异摘要，可按版本号选用）'
}
export function sourcePathLabel(source) {
  return source?.path || source?.source_root || source?.source_path || source?.name || '来源目录待核对'
}
export function sourceCleanupLabel(source, planData) {
  const cleanup = source?.cleanup ?? source?.cleanup_enabled ?? planData?.cleanup
  return cleanup ? '迁移后清理已确认复制文件' : '只复制，不清理源文件'
}
export function resultCount(value) { return Array.isArray(value) ? value.length : Number(value || 0) }
export function importedCount(value) {
  if (Array.isArray(value)) return value.length
  if (value && typeof value === 'object') {
    if (Array.isArray(value.copied)) return value.copied.length
    if (Array.isArray(value.imported)) return value.imported.length
    if (Number.isFinite(Number(value.count))) return Number(value.count)
  }
  return Number(value || 0)
}
export function isTransferIncomplete(state) { return state && state !== 'completed' }
export function transferOutcomeClass(state) {
  if (state === 'completed') return 'transfer-success'
  if (state === 'cleanup_partial' || state === 'incomplete') return 'transfer-warning'
  return 'transfer-error'
}
export function transferOutcomePrefix(state) {
  if (state === 'completed') return '✓'
  if (state === 'cleanup_partial' || state === 'incomplete') return '⚠'
  return '✗'
}
export function transferOutcomeStateText(state) {
  if (state === 'completed') return '已完成'
  if (state === 'cleanup_partial') return '复制完成，但清理未完成'
  if (state === 'incomplete') return '未完成'
  if (state === 'failed') return '失败'
  if (state === 'cancelled') return '已取消'
  return state || '状态待核对'
}
export function transferOutcomeLabel(state) { return `${transferOutcomePrefix(state)} ${transferOutcomeStateText(state)}` }
export function formatBytes(value) {
  const n = Number(value || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

