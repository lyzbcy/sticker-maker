const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron')
const fs = require('fs')
const path = require('path')
const { PythonBridge } = require('./pythonBridge')

let bridge
let mainWindow
let diagnosticLog
let operationSequence = 0

// 单实例锁：防止多开（Agent 端口 7432 会冲突，双开还会重复跑引擎）
// 开发模式用独立 userData（2026-09-03 事故：用户同时开着安装版「表情包一键制作.exe」，
// 两者同 app 名——单实例锁跨安装版/开发版生效 + 共享 user-data 目录被锁，
// 开发版启动即静默退出且无任何报错。独立目录后互不干扰。）
if (process.env.STICKER_DESKTOP_USER_DATA) {
  app.setPath('userData', path.resolve(process.env.STICKER_DESKTOP_USER_DATA))
}
if (!app.isPackaged && !process.env.STICKER_DESKTOP_USER_DATA) {
  app.setPath('userData', app.getPath('userData') + '-dev')
}

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
    show: process.env.STICKER_DESKTOP_HIDE_WINDOW !== '1',
    width: 960, height: 680, minWidth: 800, minHeight: 600,
    title: '表情包一键制作',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    titleBarOverlay: process.platform === 'win32' ? { color: '#FAF6EB', symbolColor: '#1E3A24', height: 32 } : false,
    icon: path.join(app.getAppPath(), 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true, nodeIntegration: false,
      backgroundThrottling: process.env.STICKER_DESKTOP_HIDE_WINDOW !== '1',
      offscreen: process.env.STICKER_DESKTOP_HIDE_WINDOW === '1',
      // 仅 dev 关 webSecurity：dev 页面是 http://localhost:5173，默认策略
      // 拦截 http 页面加载 file:// 缩略图 → 全部作品/详情破图（"Not allowed
      // to load local resource"）。生产 loadFile 本身就是 file:// 同源，不受影响。
      webSecurity: !process.env.VITE_DEV_SERVER_URL,
    },
  })
  mainWindow.on('closed', () => { mainWindow = null })
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

app.whenReady().then(async () => {
  // 去掉默认菜单栏（Windows 上会显示英文 File/Edit/View，粉丝版不需要）
  Menu.setApplicationMenu(null)
  app.setAppUserModelId('com.lyzbcy.sticker-maker')

  const isPackaged = app.isPackaged
  const { DiagnosticLog } = require('./diagnosticLog')
  diagnosticLog = new DiagnosticLog(path.join(app.getPath('userData'), 'diagnostics'))
  await diagnosticLog.init()
  bridge = new PythonBridge(isPackaged ? 'packaged' : 'dev')
  bridge.logger = diagnosticLog
  console.log('[main] isPackaged=', isPackaged, 'cliPath=', isPackaged ? 'packaged' : 'dev')
  bridge.start()
  bridge.on('exit', (code) => {
    diagnosticLog.log({ stage:'engine', level:code ? 'error' : 'info', message:`引擎退出 code=${code}` })
    console.log('[main] python cli exited code=', code)
    mainWindow && mainWindow.webContents.send('python-exit', { code })
  })
  bridge.on('restarting', () => {
    mainWindow && mainWindow.webContents.send('python-restarting', {})
  })

  ipcMain.handle('python-command', async (event, { cmd, args }) => {
    const labels = { run:'制作表情', run_batch:'批量制作', publish_episode:'投稿', sync_platform_status:'同步状态', sync_sticker_metrics:'读取单图发送报告', shelf_passed:'一键上架', install_codex:'安装生图组件', install_chromium:'安装浏览器', list_episodes:'读取作品', project_location_inspect:'识别资源位置', project_location_connect:'连接资源' }
    const tracked = !!labels[cmd] || /^(project_|library_)(?!status)/.test(cmd)
    const task = { id:String(++operationSequence), command:cmd, startedAt:Date.now(), message:labels[cmd] || '处理资源任务' }
    const notify = data => { if(tracked && mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('task-status', { ...task, ...data }) }
    notify({ state:'start' })
    try {
      const result = await bridge.send(cmd, args, (ev) => {
        mainWindow && mainWindow.webContents.send('python-progress', ev)
        notify({ state:'progress', message:ev.message, stage:ev.stage, percent:ev.percent })
      })
      diagnosticLog.log({ stage:'command', message:`${cmd} ${result.status || '完成'}，耗时 ${((Date.now()-task.startedAt)/1000).toFixed(1)} 秒` })
      return result
    } catch (err) {
      // 失败原因统一拍平成 errors 数组（此前只有 error 字段，
      // 前端读 errors[0].message 读不到 → 全显示"未知原因"）
      return PythonBridge.flattenError(err)
    } finally {
      notify({ state:'end' })
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
      title: '选择文件夹',
      properties: ['openDirectory'],
    })
    if (result.canceled || result.filePaths.length === 0) return { canceled: true }
    return { canceled: false, path: result.filePaths[0] }
  })

  // 2026-09-05 评审：base 图批量上传（此前只能单选，传 6 张要重复 6 遍）
  ipcMain.handle('select-files', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择 base 图（可多选）',
      filters: [{ name: '图片', extensions: ['png', 'jpg', 'jpeg'] }],
      properties: ['openFile', 'multiSelections'],
    })
    if (result.canceled || result.filePaths.length === 0) return { canceled: true }
    return { canceled: false, paths: result.filePaths }
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

  ipcMain.handle('export-episode', async (_e, episodePath) => {
    const result = await dialog.showSaveDialog(mainWindow, { title: '保存表情包', defaultPath: '我的表情包.zip', filters: [{ name: 'ZIP 表情包', extensions: ['zip'] }] })
    if (result.canceled || !result.filePath) return { canceled: true }
    try { return await bridge.send('export_episode', { path: episodePath, destination: result.filePath }) }
    catch (error) { return PythonBridge.flattenError(error) }
  })

  ipcMain.handle('send-feedback', async (_e, payload) => {
    const { sendFeedback } = require('./feedback')
    const { net } = require('electron')
    return sendFeedback(payload, { version: app.getVersion(), fetchFn: net.fetch, storageDir: app.getPath('userData') })
  })

  ipcMain.handle('diagnostics-snapshot', async () => diagnosticLog.snapshot())
  ipcMain.handle('diagnostics-mode', async (_e, value) => diagnosticLog.setDebug(value))
  ipcMain.handle('diagnostics-activity', (_e, entry) => {
    diagnosticLog.log({ stage:entry?.stage || 'ui', message:entry?.message || '', level:entry?.level || 'info' })
  })
  ipcMain.handle('diagnostics-export', async () => {
    const result = await dialog.showSaveDialog(mainWindow, { title:'导出脱敏诊断日志', defaultPath:'表情包诊断日志.jsonl', filters:[{ name:'诊断日志', extensions:['jsonl'] }] })
    if (result.canceled || !result.filePath) return { canceled:true }
    const snapshot = await diagnosticLog.snapshot(20*1024*1024, true)
    await fs.promises.writeFile(result.filePath, snapshot.text, 'utf8')
    return { ok:true, lines:snapshot.lines }
  })
  process.on('uncaughtExceptionMonitor', error => diagnosticLog.log({ stage:'app', level:'error', message:error.stack || error.message }))
  app.on('render-process-gone', (_event, _contents, details) => diagnosticLog.log({ stage:'renderer', level:'error', message:`界面进程退出 ${details.reason}` }))

  ipcMain.handle('check-for-updates', async () => {
    const { checkForUpdates } = require('./updater')
    return checkForUpdates(mainWindow, { manual: true })
  })

  createWindow()
  if (app.isPackaged && process.platform === 'win32') {
    const { confirmUpdateRestart } = require('./update-handoff')
    const { shell } = require('electron')
    confirmUpdateRestart(path.join(app.getPath('userData'), 'update-result.json'), {
      version: app.getVersion(), executable: process.execPath, readShortcut: shell.readShortcutLink
    }).catch(error => console.error('[updater] restart confirmation:', error.message))
  }

  // 启动 2 秒后检查更新（每天只自动检查一次：prompt「自适应更新检测」——
  // 每次启动都查既费流量也容易打扰，同一天内重复启动直接跳过；手动检查不受限）
  const { checkForUpdates } = require('./updater')
  setTimeout(() => {
    if (shouldAutoCheckToday()) checkForUpdates(mainWindow)
  }, 2000)

})

/** 每日首检门控：userData/update-check.json 记录上次自动检查日期，
 * 同一天内的后续启动不再自动查（手动「检查更新」不经过这里）。 */
function shouldAutoCheckToday() {
  try { return require('./update-state').recordAttempt(app.getPath('userData')) }
  catch { return false }
}

app.on('window-all-closed', () => { if(process.platform !== 'darwin') app.quit(); else bridge?.stopAll() })
app.on('activate', () => { if(BrowserWindow.getAllWindows().length === 0) { bridge?.start(); createWindow() } })
let quitting = false
app.on('before-quit', event => {
  if (quitting) return
  event.preventDefault(); quitting = true
  ;(async () => {
    if(bridge) await bridge.stopAll()
    if(diagnosticLog) { diagnosticLog.log({stage:'app',message:'应用正常退出'}); await diagnosticLog.close() }
  })().finally(() => app.quit())
})
