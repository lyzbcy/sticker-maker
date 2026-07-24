const { spawn } = require('child_process')
const { EventEmitter } = require('events')
const path = require('path')

/**
 * PythonBridge: 常驻 spawn sticker-engine-cli，通过 stdin/stdout JSON-lines 通信。
 * - send(cmd, args, progressCb) 返回 Promise，result.ok resolve / fail reject
 * - progress 事件经 progressCb 和 'progress' EventEmitter 事件流出
 * - 进程崩溃自动 reject 所有 pending
 */
class PythonBridge extends EventEmitter {
  constructor(cliPath) {
    super()
    this.cliPath = cliPath   // 'dev' | 'packaged' | 绝对路径
    this.proc = null
    this.reqId = 0
    this.pending = new Map()   // {reqId -> {resolve, reject, progressCb}}
    this._buffer = ''
  }

  start() {
    if (this.proc) return
    let cmd, args
    if (this.cliPath === 'dev') {
      cmd = '/Users/zeen/Documents/共享/星星布丁/微信表情包/sticker_engine/.venv/bin/python'
      args = ['-m', 'sticker_engine.cli']
    } else if (this.cliPath === 'packaged') {
      cmd = path.join(process.resourcesPath, 'sticker-engine-cli')
      args = []
    } else {
      cmd = this.cliPath
      args = []
    }
    this.proc = spawn(cmd, args, { cwd: path.dirname(cmd) || undefined })
    this.proc.stdout.setEncoding('utf-8')
    this.proc.stdout.on('data', (data) => this._onData(data))
    this.proc.stderr.on('data', (data) => {
      console.error('[cli stderr]', data.toString())
    })
    this.proc.on('exit', (code) => {
      this.emit('exit', code)
      this.proc = null
      for (const [, p] of this.pending) {
        p.reject(new Error(`CLI 进程退出 (code=${code})`))
      }
      this.pending.clear()
    })
  }

  _onData(data) {
    this._buffer += data
    let nl
    while ((nl = this._buffer.indexOf('\n')) >= 0) {
      const line = this._buffer.slice(0, nl).trim()
      this._buffer = this._buffer.slice(nl + 1)
      if (!line) continue
      try {
        const ev = JSON.parse(line)
        this._handleEvent(ev)
      } catch (e) {
        console.error('[协议解析失败]', line, e)
      }
    }
  }

  _handleEvent(ev) {
    const id = ev.id
    const pending = this.pending.get(id)
    if (ev.type === 'progress') {
      if (pending) {
        pending.progressCb && pending.progressCb(ev)
      }
      this.emit('progress', ev)
    } else if (ev.type === 'result') {
      if (pending) {
        this.pending.delete(id)
        if (ev.status === 'ok') pending.resolve(ev)
        else pending.reject(ev)
      }
    } else if (ev.type === 'error') {
      if (pending) {
        this.pending.delete(id)
        pending.reject(ev)
      } else {
        // 无 pending 的 error（如协议级错误），也 emit 出去
        this.emit('protocol-error', ev)
      }
    }
  }

  send(cmd, args = {}, progressCb = null) {
    return new Promise((resolve, reject) => {
      if (!this.proc) {
        reject(new Error('CLI 未启动'))
        return
      }
      const id = `req-${++this.reqId}`
      this.pending.set(id, { resolve, reject, progressCb })
      this.proc.stdin.write(JSON.stringify({ id, cmd, args }) + '\n')
    })
  }

  stop(targetId) {
    return this.send('stop', { target_id: targetId })
  }

  async stopAll() {
    if (this.proc) {
      this.proc.kill()
      this.proc = null
    }
  }
}

module.exports = { PythonBridge }
