const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { PythonBridge } = require('./pythonBridge')

let bridge
let mainWindow

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960, height: 680, minWidth: 800, minHeight: 600,
    title: '表情包一键制作',
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true, nodeIntegration: false,
    },
  })
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  const isPackaged = app.isPackaged
  bridge = new PythonBridge(isPackaged ? 'packaged' : 'dev')
  bridge.start()
  bridge.on('exit', (code) => {
    mainWindow && mainWindow.webContents.send('python-exit', { code })
  })

  ipcMain.handle('python-command', async (event, { cmd, args }) => {
    try {
      const result = await bridge.send(cmd, args, (ev) => {
        mainWindow && mainWindow.webContents.send('python-progress', ev)
      })
      return result
    } catch (err) {
      return { status: 'fail', error: err.message || String(err), raw: err }
    }
  })

  ipcMain.handle('python-stop', async (event, targetId) => {
    return bridge.stop(targetId)
  })

  createWindow()

  // 启动 2 秒后检查更新
  const { checkForUpdates } = require('./updater')
  setTimeout(() => checkForUpdates(mainWindow), 2000)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', async () => {
  if (bridge) await bridge.stopAll()
  if (process.platform !== 'darwin') app.quit()
})
