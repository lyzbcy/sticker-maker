// Missing data remains null; never estimate individual usage from album totals.
export function metric(value) {
  if (value == null || String(value).trim() === '') return null
  const text = String(value).trim().replace(/,/g, '')
  if (!/^\d+(?:\.\d+)?$/.test(text)) return null
  const n = Number(text)
  return Number.isFinite(n) && n >= 0 ? n : null
}
export function albumMetrics(episodes) {
  const seen = new Set()
  return episodes.filter(ep => {
    const id = ep.platform_item_id || ep.work_id || ep.path || ep.name
    if (!id || seen.has(id)) return false
    seen.add(id); return true
  }).map(ep => ({ ...ep, sends: metric(ep.platform_sends), downloads: metric(ep.platform_downloads), tips: metric(ep.platform_tips) }))
}
export function rank(rows, key) {
  return [...rows].sort((a, b) => (a[key] == null) - (b[key] == null) || (b[key] ?? 0) - (a[key] ?? 0))
}
export function total(rows, key) {
  const known = rows.filter(r => r[key] != null)
  return { value: known.length ? known.reduce((n, r) => n + r[key], 0) : null, known: known.length }
}
