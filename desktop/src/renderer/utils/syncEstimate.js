// Estimates, not promises. Prefer this device's observed wall time; otherwise
// allow for list/login/library overhead and ~3 bounded detail requests at once.
export function estimateSync(episodes = [], history = null) {
  const rejected = episodes.filter(ep => ep.platform_status === '未通过审核')
  const pending = rejected.filter(ep => !ep.platform_reject_reason ||
    !ep.platform_review_cycle || ep.platform_reject_checked_cycle !== ep.platform_review_cycle).length
  const usable = history && Number.isFinite(history.baseSeconds) && history.baseSeconds > 0
  const base = usable ? history.baseSeconds : Math.max(12, 8 + episodes.length * 0.025)
  const perReason = Number.isFinite(history?.perReasonSeconds) && history.perReasonSeconds > 0
    ? history.perReasonSeconds : 0.55
  const extra = pending ? 3 + pending * perReason : 0
  const range = seconds => {
    const lo = Math.max(5, Math.ceil(seconds * 0.65 / 5) * 5)
    const hi = Math.max(lo + 5, Math.ceil(seconds * 1.8 / 5) * 5)
    const fmt = n => n < 60 ? `${n} 秒` : `${Math.floor(n / 60)} 分${n % 60 ? ` ${n % 60} 秒` : ''}`
    return `约 ${fmt(lo)}–${fmt(hi)}`
  }
  return { rejected: rejected.length, pending, fast: range(base),
    withReasons: range(base + extra), measured: Boolean(usable) }
}

export function recordSyncTiming(result, wallSeconds, previous = null) {
  if (result?.source !== 'api' || result.cancelled || !Number.isFinite(wallSeconds)) return previous
  const reasonSeconds = Number(result.reason_seconds) || 0
  const count = (Number(result.reasons_fetched) || 0) + (result.reason_failures?.length || 0)
  return { baseSeconds: Math.max(1, wallSeconds - reasonSeconds),
    perReasonSeconds: count ? reasonSeconds / count : previous?.perReasonSeconds }
}
