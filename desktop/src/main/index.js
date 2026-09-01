const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron')
const fs = require('fs')
const path = require('path')
const { PythonBridge } = require('./pythonBridge')

let bridge
let mainWindow

// 单实例锁：防止多开（Agent 端口 7432 会冲突，双开还会重复跑引擎）
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960, height: 680, minWidth: 800, minHeight: 600,
    title: '表情包一键制作',
    icon: path.join(____, 'build', 'icon.png').replace('mainuild', 'build'),
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
  // 去掉默认菜单栏（Windows 上会显示英文 File/Edit/View，粉丝版不需要）
  Menu.setApplicationMenu(null)

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

  // 打开外部链接（关于页/求好评一键直达；集中管控协议白名单）
  ipcMain.handle('open-external', async (_e, url) => {
    const { shell } = require('electron')
    if (typeof url === 'string' && /^https:\/\//.test(url)) {
      await shell.openExternal(url)
      return { ok: true }
    }
    return { ok: false }
  })

  // 复制到系统剪贴板（可等待、回报长度，方便前端确认成败）
  const { clipboard } = require('electron')
  ipcMain.handle('copy-text', async (_e, text) => {
    const s = String(text == null ? '' : text)
    clipboard.writeText(s)
    return { ok: true, length: s.length }
  })

  ipcMain.handle('check-for-updates', async () => {
    const { checkForUpdates } = require('./updater')
    return checkForUpdates(mainWindow, { manual: true })
  })

  createWindow()

  // 启动 2 秒后检查更新（每天只自动检查一次：prompt「自适应更新检测」——
  // 每次启动都查既费流量也容易打扰，同一天内重复启动直接跳过；手动检查不受限）
  const { checkForUpdates } = require('./updater')
  setTimeout(() => {
    if (shouldAutoCheckToday()) checkForUpdates(mainWindow)
  }, 2000)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

/** 每日首检门控：userData/update-check.json 记录上次自动检查日期，
 * 同一天内的后续启动不再自动查（手动「检查更新」不经过这里）。 */
function shouldAutoCheckToday() {
  try {
    const stateFile = path.join(app.getPath('userData'), 'update-check.json')
    const today = new Date().toISOString().slice(0, 10)
    let last = ''
    try {
      last = JSON.parse(fs.readFileSync(stateFile, 'utf-8')).lastDate || ''
    } catch { /* 首次或文件损坏都视为需要检查 */ }
    if (last === today) return false
    fs.writeFileSync(stateFile, JSON.stringify({ lastDate: today }))
    return true
  } catch (error) {
    console.error('[updater] 读写检查日期失败，默认执行检查', error)
    return true
  }
}

app.on('window-all-closed', async () => {
  if (bridge) await bridge.stopAll()
  if (process.platform !== 'darwin') app.quit()
})
