const fs = require('node:fs/promises')
const path = require('node:path')
const crypto = require('node:crypto')
const { scrubText } = require('./diagnostics')

class DiagnosticLog {
  constructor(root, { interval = 5000, batchBytes = 65536, fileBytes = 2*1024*1024,
    totalBytes = 20*1024*1024, retentionMs = 7*86400000, now = Date.now } = {}) {
    Object.assign(this, { root, batchBytes, fileBytes, totalBytes, retentionMs, now })
    this.queue = []; this.bytes = 0; this.ring = []; this.debug = false; this.error = ''
    this.session = `${now()}-${crypto.randomUUID().slice(0,8)}`; this.index = 0; this.size = 0
    this.timer = setInterval(() => this.flush(), interval); this.timer.unref?.()
  }
  async init() {
    try { this.debug = !!JSON.parse(await fs.readFile(path.join(this.root, 'config.json'), 'utf8')).debug }
    catch (e) { if (e.code !== 'ENOENT') this.error = '日志设置读取失败' }
    await this.prune().catch(() => {})
    this.log({ stage: 'app', message: '应用启动', level: 'info' })
  }
  log({ stage = 'app', message = '', level = 'info', requestId, details } = {}) {
    const entry = { time: new Date(this.now()).toISOString(), session: this.session,
      level, stage: scrubText(stage).slice(0,80), message: scrubText(message).slice(0,4000) }
    if (requestId) entry.requestId = scrubText(requestId).slice(0,80)
    if (this.debug && details !== undefined) entry.details = scrubText(JSON.stringify(details)).slice(0,4000)
    const line = JSON.stringify(entry)+'\n'
    this.ring.push(line); if (this.ring.length > 2000) this.ring.shift()
    this.queue.push(line); this.bytes += Buffer.byteLength(line)
    // A failing disk must not grow memory without limit.
    while (this.bytes > 512*1024 && this.queue.length > 1) this.bytes -= Buffer.byteLength(this.queue.shift())
    if (this.bytes >= this.batchBytes || level === 'error') void this.flush()
  }
  async flush() {
    if (this.work) return this.work
    if (!this.queue.length) return
    this.work = (async () => {
      const batch = this.queue.splice(0), text = batch.join(''), length = Buffer.byteLength(text)
      this.bytes = 0
      try {
        await fs.mkdir(this.root, { recursive: true })
        if (this.size && this.size + length > this.fileBytes) { this.index++; this.size = 0 }
        await fs.appendFile(path.join(this.root, `${this.session}-${String(this.index).padStart(4,'0')}.jsonl`), text, 'utf8')
        this.size += length
        this.error = ''
        await this.prune().catch(() => { this.error = '旧日志清理失败，请检查目录权限。' })
      } catch {
        this.queue.unshift(...batch)
        this.bytes = this.queue.reduce((n,s) => n+Buffer.byteLength(s),0)
        while (this.bytes > 512*1024 && this.queue.length > 1) this.bytes -= Buffer.byteLength(this.queue.shift())
        this.error = '本地日志写入失败，请检查磁盘空间或权限；仍保留最近的内存记录。'
      }
    })()
    await this.work; this.work = null
  }
  async files() {
    try {
      const names = (await fs.readdir(this.root)).filter(n => /^\d+-[a-f0-9]+-\d+\.jsonl$/.test(n))
      const entries = await Promise.all(names.map(async n => ({ name:n, ...(await fs.stat(path.join(this.root,n))) })))
      return entries.sort((a,b) => a.mtimeMs-b.mtimeMs || a.name.localeCompare(b.name))
    } catch (e) { if (e.code === 'ENOENT') return []; throw e }
  }
  async prune() {
    const files = await this.files(); let bytes = files.reduce((n,f) => n+f.size,0)
    for (const f of files) if (this.now()-f.mtimeMs > this.retentionMs || bytes > this.totalBytes) {
      await fs.unlink(path.join(this.root, f.name)); bytes -= f.size
    }
  }
  async setDebug(value) {
    if (typeof value !== 'boolean') throw Error('无效排障模式')
    await fs.mkdir(this.root, { recursive: true })
    await fs.writeFile(path.join(this.root,'config.json'), JSON.stringify({ debug:value }))
    this.debug = value; this.log({ stage:'diagnostics', message:value ? '已开启详细排障日志' : '已关闭详细排障日志' })
    return this.status()
  }
  status() { return { debug:this.debug, error:this.error, retentionDays:7, maxMB:20 } }
  async snapshot(maxBytes = 8000, raw = false) {
    await this.flush()
    let text = ''
    const files = await this.files().catch(() => [])
    for (const file of files.reverse()) {
      text = (await fs.readFile(path.join(this.root,file.name),'utf8')) + text
      if (Buffer.byteLength(text) >= maxBytes*4) break
    }
    if (this.error) text += this.ring.join('')
    const lines = text.trimEnd().split('\n').filter(Boolean).map(line => {
      if (raw) return line
      try { const e = JSON.parse(line); return `${e.time} [${e.stage}] ${e.message}${e.details ? '\n'+e.details : ''}` }
      catch { return scrubText(line) }
    }), selected = []; let bytes = 0
    for (const line of lines.reverse()) {
      const length = Buffer.byteLength(line+'\n')
      if (bytes+length > maxBytes) {
        if (!selected.length && !raw) selected.push('…'+Buffer.from(line).subarray(-(maxBytes-8)).toString('utf8').replace(/^\uFFFD+/, ''))
        break
      }
      selected.unshift(line); bytes += length
    }
    return { ...this.status(), text:selected.join('\n'), lines:selected.length, bytes:Buffer.byteLength(selected.join('\n')),
      scope: maxBytes < this.totalBytes ? '最近诊断记录（含此前运行，按大小限制）' : '本机保留的诊断记录' }
  }
  async close() {
    clearInterval(this.timer)
    if (this.work) await this.work
    await this.flush()
  }
}
module.exports = { DiagnosticLog }
