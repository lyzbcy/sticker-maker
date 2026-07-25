const { app, BrowserWindow, ipcMain, dialog } = require('electron')
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
    // 打包模式：dist 在 app.asar 内，用 app.getAppPath() 定位更稳
    mainWindow.loadFile(path.join(app.getAppPath(), 'dist', 'index.html'))
  }
  // 诊断模式：设环境变量 STICKER_DEVTOOLS=1 时开 DevTools（默认关，避免给粉丝的版本带 DevTools）
  if (process.env.STICKER_DEVTOOLS === '1') {
    mainWindow.webContents.on('did-finish-load', () => {
      mainWindow.webContents.openDevTools({ mode: 'detach' })
    })
  }
}

app.whenReady().then(() => {
  const isPackaged = app.isPackaged
  bridge = new PythonBridge(isPackaged ? 'packaged' : 'dev')
  console.log('[main] isPackaged=', isPackaged, 'cliPath=', isPackaged ? 'packaged' : 'dev')
  bridge.start()
  bridge.on('exit', (code) => {
    console.log('[main] python cli exited code=', code)
    mainWindow && mainWindow.webContents.send('python-exit', { code })
  })
  bridge.on('restarting', () => {
    mainWindow && mainWindow.webContents.send('python-restarting', {})
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

  // C1 修复：文件选择（上传 base 图）
  ipcMain.handle('select-file', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择 base 图',
      filters: [{ name: '图片', extensions: ['png', 'jpg', 'jpeg'] }],
      properties: ['openFile'],
    })
    if (result.canceled || result.filePaths.length === 0) return { canceled: true }
    return { canceled: false, path: result.filePaths[0] }
  })

  // I2 修复：目录选择（参考图库位置）
  ipcMain.handle('select-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择参考图库文件夹',
      properties: ['openDirectory'],
    })
    if (result.canceled || result.filePaths.length === 0) return { canceled: true }
    return { canceled: false, path: result.filePaths[0] }
  })

  ipcMain.handle('check-for-updates', async () => {
    const { checkForUpdates } = require('./updater')
    return checkForUpdates(mainWindow, { manual: true })
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
