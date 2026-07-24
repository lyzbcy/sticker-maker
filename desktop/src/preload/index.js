const { contextBridge, ipcRenderer } = require('electron')

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
})
