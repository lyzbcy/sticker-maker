/**
 * 平台驳回理由解析：多行原文 → 结构化条目 [{group, text}]。
 *
 * 理由页原文结构（2026-08-29 实测）：组名行（表情名称/聊天页图标/总体驳回理由…）
 * + 理由文本行成对出现；中间可能混入专辑名行（如「周三涵做表情 62」，需过滤）；
 * 同一组可能连续多条文本（如聊天页图标两条），合并为一条目的多段。
 */

export function parseReasonItems(text, albumName) {
  const lines = String(text || '').split(/\n+/).map(s => s.trim()).filter(Boolean)
  const norm = s => String(s || '').replace(/\s+/g, '')
  const album = norm(albumName)
  const items = []
  let cur = null
  for (const line of lines) {
    if (line === '表情驳回理由') continue
    if (album && norm(line) === album) continue          // 专辑名行滤掉
    // 组名行：短且不以标点收尾（理由文本总是长句/以句号收尾）
    const isGroup = line.length <= 12 && !/[。！？.!?，,…]$/.test(line)
    if (isGroup) {
      cur = items.find(it => it.group === line) || null   // 同组复用（多段合一）
      if (!cur) { cur = { group: line, text: '' }; items.push(cur) }
    } else if (cur) {
      cur.text += (cur.text ? '\n' : '') + line
    } else {
      items.push({ group: '', text: line })
    }
  }
  return items.filter(it => it.text || it.group)
}

export function reasonCount(text, albumName) {
  // 条数按"文本段"计（同组两段=两条理由，与平台驳回条数对齐）
  return parseReasonItems(text, albumName)
    .reduce((n, it) => n + it.text.split('\n').filter(Boolean).length, 0)
}
