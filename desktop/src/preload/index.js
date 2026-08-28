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
  // 统一深拷贝：渲染进程传入的 args 常含 Vue 响应式 Proxy，
  // Electron IPC 的 structured clone 无法序列化 Proxy（"An object could not be cloned"）。
  // 在通信层一次性剥掉，所有命令永久免疫此问题。
  send: async (cmd, args) => ipcRenderer.invoke(
    'python-command', { cmd, args: JSON.parse(JSON.stringify(args ?? {})) }),
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
  copyText: (text) => ipcRenderer.invoke('copy-text', text),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // 更新下载进度（main 的 updater 流式回报：stage=download/verify, percent, MB）
  onUpdateProgress: (cb) => {
    ipcRenderer.on('update-progress', (_, ev) => cb(ev))
  },
}

if (contextBridge && contextBridge.exposeInMainWorld) {
  contextBridge.exposeInMainWorld('api', api)
}

module.exports = { toFileUrl }
