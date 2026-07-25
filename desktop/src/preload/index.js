const { contextBridge, ipcRenderer, clipboard } = require('electron')

function toFileUrl(filePath) {
  if (!filePath) return ''
  const normalized = String(filePath).replace(/\\/g, '/')
  if (normalized.startsWith('file://')) return normalized
  const absolutePath = normalized.startsWith('/') ? normalized : `/${normalized}`
  return `file://${absolutePath.split('/').map(segment => encodeURIComponent(segment)).join('/')}`
}

// 暴露给渲染进程的安全 API（contextIsolation）
const api = {
  send: async (cmd, args) => ipcRenderer.invoke('python-command', { cmd, args }),
  stop: (targetId) => ipcRenderer.invoke('python-stop', targetId),
  onProgress: (cb) => {
    ipcRenderer.on('python-progress', (_, ev) => cb(ev))
  },
  onExit: (cb) => {
    ipcRenderer.on('python-exit', (_, data) => cb(data))
  },
  onRestarting: (cb) => {
    ipcRenderer.on('python-restarting', (_, data) => cb(data))
  },
  selectFile: async () => ipcRenderer.invoke('select-file'),
  selectDirectory: async () => ipcRenderer.invoke('select-directory'),
  toFileUrl,
  copyText: (text) => clipboard.writeText(String(text || '')),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
}

if (contextBridge && contextBridge.exposeInMainWorld) {
  contextBridge.exposeInMainWorld('api', api)
}

module.exports = { toFileUrl }
