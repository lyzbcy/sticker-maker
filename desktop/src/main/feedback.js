const { scrubText } = require('./diagnostics')
const FEEDBACK_URL = process.env.STICKER_FEEDBACK_URL || require('./feedback-config.json').publicUrl
let sending = false, lastSent = 0
async function sendFeedback(payload, { version, fetchFn = fetch, endpoint = FEEDBACK_URL } = {}) {
  const message = scrubText(payload?.message).trim()
  if (!message || message.length > 1500) return { ok: false, error: '请填写 1–1500 字的留言' }
  if (sending || Date.now() - lastSent < 30000) return { ok: false, error: '请稍等半分钟后再发送' }
  if (!endpoint) return { ok: false, error: '反馈接收服务尚未配置，请先复制诊断信息联系作者。' }
  sending = true
  try {
    const content = `表情包一键制作 ${version}\n${scrubText(payload.category).slice(0, 40)}\n${message}\n${scrubText(payload.logs).slice(-1000)}`
    const response = await fetchFn(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msgtype: 'text', text: { content } }), signal: AbortSignal.timeout(15000) })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.errcode !== 0) throw new Error('反馈服务暂时繁忙')
    lastSent = Date.now()
    return { ok: true }
  } catch { return { ok: false, error: '网络或反馈服务暂时不可用' } }
  finally { sending = false }
}
module.exports = { sendFeedback }
