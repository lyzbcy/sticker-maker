const { contextBridge, ipcRenderer, clipboard } = require('electron')
const { pathToFileURL } = require('url')

// 暴露给渲染进程的安全 API（contextIsolation）
contextBridge.exposeInMainWorld('api', {
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
  toFileUrl: (filePath) => filePath ? pathToFileURL(filePath).href : '',
  copyText: (text) => clipboard.writeText(String(text || '')),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
})
