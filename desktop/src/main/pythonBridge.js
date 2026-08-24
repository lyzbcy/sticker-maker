const { spawn } = require('child_process')
const { EventEmitter } = require('events')
const path = require('path')

/**
 * PythonBridge: 常驻 spawn sticker-engine-cli，通过 stdin/stdout JSON-lines 通信。
 * - send(cmd, args, progressCb) 返回 Promise，result.ok resolve / fail reject
 * - progress 事件经 progressCb 和 'progress' EventEmitter 事件流出
 * - 进程崩溃自动 reject 所有 pending
 */
/**
 * 解析 CLI 可执行路径（packaged 模式）。
 * onedir 产物：resources/sticker-engine-cli/sticker-engine-cli(.exe)
 */
function resolvePackagedCliPath(resourcesPath, platform = process.platform) {
  const exeName = platform === 'win32' ? 'sticker-engine-cli.exe' : 'sticker-engine-cli'
  return path.join(resourcesPath, 'sticker-engine-cli', exeName)
}

/**
 * 解析 dev 模式的 venv python 路径（相对仓库根的 sticker_engine/.venv）。
 * 可用环境变量 STICKER_ENGINE_PYTHON 覆盖（本机 venv 不在默认位置时）。
 */
function resolveDevPython(repoRoot, platform = process.platform) {
  if (process.env.STICKER_ENGINE_PYTHON) return process.env.STICKER_ENGINE_PYTHON
  const venvPython = platform === 'win32'
    ? ['sticker_engine', '.venv', 'Scripts', 'python.exe']
    : ['sticker_engine', '.venv', 'bin', 'python']
  return path.join(repoRoot, ...venvPython)
}

class PythonBridge extends EventEmitter {
  constructor(cliPath) {
    super()
    this.cliPath = cliPath   // 'dev' | 'packaged' | 绝对路径
    this.proc = null
    this.reqId = 0
    this.pending = new Map()   // {reqId -> {resolve, reject, progressCb}}
    this.currentRunId = null
    this._buffer = ''
    this._stopped = false   // true 表示主动 stopAll，不要自动重启
  }

  start() {
    if (this.proc) return
    this._stopped = false
    let cmd, args
    if (this.cliPath === 'dev') {
      // desktop/src/main → 上三级 = 仓库根
      const repoRoot = path.join(__dirname, '..', '..', '..')
      cmd = resolveDevPython(repoRoot)
      args = ['-m', 'sticker_engine.cli']
    } else if (this.cliPath === 'packaged') {
      cmd = resolvePackagedCliPath(process.resourcesPath)
      args = []
    } else {
      cmd = this.cliPath
      args = []
    }
    this.proc = spawn(cmd, args, { cwd: path.dirname(cmd) || undefined })
    this.proc.on('error', (err) => {
      console.error('[pythonBridge] spawn ERROR:', err.message, err.code)
    })
    this.proc.stdout.setEncoding('utf-8')
    this.proc.stdout.on('data', (data) => {
      console.log('[cli stdout]', data.toString().trim())
      this._onData(data)
    })
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
      this.currentRunId = null
      // C3 修复：崩溃（非主动关闭）自动重启
      if (!this._stopped) {
        console.error('[pythonBridge] CLI 崩溃，3 秒后自动重启...')
        this.emit('restarting')
        setTimeout(() => this.start(), 3000)
      }
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
        // run 结束后清当前 run 标记
        if (id === this.currentRunId) this.currentRunId = null
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
      // C2 修复：追踪当前 run 的 id，stop 不传 target 时停它
      if (cmd === 'run') {
        this.currentRunId = id
      }
      this.proc.stdin.write(JSON.stringify({ id, cmd, args }) + '\n')
    })
  }

  stop(targetId) {
    // C2 修复：targetId 缺省时用当前 run 的 id（前端不知道真实 reqId）
    const realTarget = targetId && targetId !== 'all' ? targetId : this.currentRunId
    if (!realTarget) return Promise.reject(new Error('无正在运行的任务'))
    return this.send('stop', { target_id: realTarget })
  }

  async stopAll() {
    this._stopped = true   // 标记主动关闭，阻止自动重启
    if (this.proc) {
      this.proc.kill()
      this.proc = null
    }
  }
}

module.exports = { PythonBridge, resolvePackagedCliPath, resolveDevPython }
