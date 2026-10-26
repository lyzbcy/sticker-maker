// Compare only the same captured day + literal platform reporting date.
// Platform Report.SendNum is daily, not the album's TotalSendNum.
export function singleMetrics(albums = []) {
  const latest = new Map()
  for (const album of albums) {
    if (!album?.item_id || album.period_kind !== 'platform_daily') continue
    const old = latest.get(album.item_id)
    if (!old || String(album.captured_at) > String(old.captured_at)) latest.set(album.item_id, album)
  }
  return [...latest.values()].flatMap(album => {
    const seen = new Set()
    return (album.items || []).filter(item => {
      const key = `${item.md5}|${item.data_time}`
      if (!item.md5 || !item.data_time || !Number.isSafeInteger(item.sends) || item.sends < 0 || seen.has(key)) return false
      seen.add(key); return true
    }).map(item => ({ ...item, item_id: album.item_id, album_name: album.album_name,
      captured_at: album.captured_at, capture_date: album.capture_date,
      observation: `${album.capture_date} | ${item.data_time}` }))
  })
}
export function observationGroups(rows) {
  const groups = new Map()
  for (const row of [...rows].sort((a,b)=>String(b.captured_at).localeCompare(String(a.captured_at)))) {
    if (!groups.has(row.observation)) groups.set(row.observation, { key:row.observation, label:`抓取 ${row.capture_date} / 平台 ${row.data_time}` })
  }
  return [...groups.values()]
}
export function rankSingles(rows, observation) {
  return rows.filter(r=>r.observation===observation).sort((a,b)=>b.sends-a.sends || String(a.album_name).localeCompare(String(b.album_name),'zh-CN') || String(a.index).localeCompare(String(b.index)))
}
