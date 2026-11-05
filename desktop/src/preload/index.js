const { contextBridge, ipcRenderer, clipboard } = require('electron')

function toFileUrl(filePath) {
  if (!filePath) return ''
  const normalized = String(filePath).replace(/\\/g, '/')
  if (normalized.startsWith('file://')) return normalized
  const absolutePath = normalized.startsWith('/') ? normalized : `/${normalized}`
  return `file://${absolutePath.split('/').map(segment => encodeURIComponent(segment)).join('/')}`
}

// Return a per-listener, idempotent cleanup, including callbacks already queued.
function subscribe(channel, cb) {
  let active = true
  const listener = (_, value) => { if (active) cb(value) }
  ipcRenderer.on(channel, listener)
  return () => {
    if (!active) return
    active = false
    ipcRenderer.removeListener(channel, listener)
  }
}

// 暴露给渲染进程的安全 API（contextIsolation）
const api = {
  // 统一深拷贝：渲染进程传入的 args 常含 Vue 响应式 Proxy，
  // Electron IPC 的 structured clone 无法序列化 Proxy（"An object could not be cloned"）。
  // 在通信层一次性剥掉，所有命令永久免疫此问题。
  send: async (cmd, args) => ipcRenderer.invoke(
    'python-command', { cmd, args: JSON.parse(JSON.stringify(args ?? {})) }),
  stop: (targetId) => ipcRenderer.invoke('python-stop', targetId),
  onProgress: cb => subscribe('python-progress', cb),
  onExit: cb => subscribe('python-exit', cb),
  onRestarting: cb => subscribe('python-restarting', cb),
  onTask: cb => subscribe('task-status', cb),
  selectFile: async () => ipcRenderer.invoke('select-file'),
  selectFiles: async () => ipcRenderer.invoke('select-files'),
  selectDirectory: async () => ipcRenderer.invoke('select-directory'),
  toFileUrl,
  copyText: (text) => ipcRenderer.invoke('copy-text', text),
  exportEpisode: (episodePath) => ipcRenderer.invoke('export-episode', episodePath),
  sendFeedback: (payload) => ipcRenderer.invoke('send-feedback', payload),
  diagnosticSnapshot: () => ipcRenderer.invoke('diagnostics-snapshot'),
  diagnosticMode: (value) => ipcRenderer.invoke('diagnostics-mode', value),
  exportDiagnostics: () => ipcRenderer.invoke('diagnostics-export'),
  recordActivity: (entry) => ipcRenderer.invoke('diagnostics-activity', JSON.parse(JSON.stringify(entry))),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // 更新下载进度（main 的 updater 流式回报：stage=download/verify, percent, MB）
  onUpdateProgress: cb => subscribe('update-progress', cb),
}

if (contextBridge && contextBridge.exposeInMainWorld) {
  contextBridge.exposeInMainWorld('api', api)
}

module.exports = { toFileUrl }
