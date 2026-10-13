const { scrubText } = require('./diagnostics')
const fs = require('node:fs/promises'), path = require('node:path'), crypto = require('node:crypto')
const FEEDBACK_URL = process.env.STICKER_FEEDBACK_URL || require('./feedback-config.json').publicUrl
let sending = false, lastSent = 0
let memoryPending = null
async function sendFeedback(payload, { version, fetchFn = fetch, endpoint = FEEDBACK_URL, storageDir } = {}) {
  const message = scrubText(payload?.message).trim()
  if (!message || message.length > 1500) return { ok: false, error: '请填写 1–1500 字的留言' }
  if (sending || Date.now() - lastSent < 30000) return { ok: false, error: '请稍等半分钟后再发送' }
  if (!endpoint) return { ok: false, error: '反馈接收服务尚未配置，请先复制诊断信息联系作者。' }
  sending = true
  try {
    const content = `表情包一键制作 ${version}\n${scrubText(payload.category).slice(0, 40)}\n${message}\n${scrubText(payload.logs).slice(-1000)}`
    const digest = crypto.createHash('sha256').update(content).digest('hex')
    const pendingFile = storageDir && path.join(storageDir, 'feedback-pending.json')
    let pending = memoryPending
    if (pendingFile) {
      try { pending = JSON.parse(await fs.readFile(pendingFile, 'utf8')) }
      catch (error) { if (error.code !== 'ENOENT') throw Error('反馈回执记录读取失败，请先联系作者。'); pending = null }
    }
    if (pending && pending.digest !== digest) return { ok: false, error: `上一条反馈的回执待确认（${pending.id}），请先联系作者；草稿已保留。` }
    pending = pending || { id: crypto.randomUUID(), digest }
    if (pendingFile) {
      await fs.mkdir(storageDir, { recursive: true })
      await fs.writeFile(pendingFile + '.tmp', JSON.stringify(pending))
      await fs.rename(pendingFile + '.tmp', pendingFile)
    }
    memoryPending = pending
    const response = await fetchFn(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: pending.id, msgtype: 'text', text: { content } }), signal: AbortSignal.timeout(55000) })
    const data = await response.json()
    if (!response.ok || data.errcode !== 0) {
      if (data.state === 'failed' || ['rate_limited', 'invalid_length', 'invalid_request', 'invalid_message', 'invalid_product'].includes(data.error)) {
        memoryPending = null; if (pendingFile) await fs.unlink(pendingFile).catch(() => {})
      }
      return { ok: false, error: ['unknown','pending','partial'].includes(data.state) ? `反馈回执待确认（${pending.id}），暂勿重复提交；保留草稿，稍后重试查询。` : '反馈接收服务暂忙，请稍后重试。' }
    }
    memoryPending = null; if (pendingFile) await fs.unlink(pendingFile).catch(() => {})
    lastSent = Date.now()
    return { ok: true }
  } catch { return { ok: false, error: '网络或反馈回执暂时不可用；保留草稿，相同留言重试将查询同一回执。' } }
  finally { sending = false }
}
module.exports = { sendFeedback }
