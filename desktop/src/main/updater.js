const { dialog, shell } = require('electron')

// 远端版本检查地址（lyzbcy GitHub Pages）。发布时部署 version.json 到此。
const VERSION_CHECK_URL = 'https://lyzbcy.github.io/sticker-maker/version.json'

async function checkForUpdates(mainWindow) {
  try {
    const CURRENT_VERSION = require('../../package.json').version
    const res = await fetch(VERSION_CHECK_URL, { cache: 'no-store' })
    if (!res.ok) return
    const data = await res.json()
    if (data.version && data.version !== CURRENT_VERSION) {
      const choice = await dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: '发现新版本',
        message: `新版本 ${data.version} 可用（当前 ${CURRENT_VERSION}）`,
        detail: data.releaseNotes || '',
        buttons: ['一键更新', '稍后'],
        defaultId: 0,
      })
      if (choice.response === 0 && data.downloadUrl) {
        await shell.openExternal(data.downloadUrl)
      }
    }
  } catch (e) {
    // 静默失败（离线/地址未部署时不打扰用户）
    console.error('[updater] 检查失败', e)
  }
}

module.exports = { checkForUpdates }
