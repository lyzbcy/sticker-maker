const { app, dialog, shell } = require('electron')
const crypto = require('crypto')
const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { execFile, spawn } = require('child_process')
const { promisify } = require('util')

const execFileAsync = promisify(execFile)

// 远端版本检查地址（lyzbcy GitHub Pages）。发布时部署 version.json 到此。
const VERSION_CHECK_URL = 'https://lyzbcy.github.io/sticker-maker/version.json'
const PRODUCT_NAME = '表情包一键制作'

function versionParts(version) {
  return String(version || '')
    .replace(/^v/i, '')
    .split('.')
    .map(part => Number.parseInt(part, 10) || 0)
}

function isNewerVersion(remote, current) {
  const left = versionParts(remote)
  const right = versionParts(current)
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    const a = left[index] || 0
    const b = right[index] || 0
    if (a !== b) return a > b
  }
  return false
}

function validateDownloadUrl(value) {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

async function verifyChecksum(filePath, expected) {
  if (!expected) return true
  const data = await fs.readFile(filePath)
  const actual = crypto.createHash('sha256').update(data).digest('hex')
  return actual.toLowerCase() === String(expected).toLowerCase()
}

async function findInstaller(extractDir) {
  const direct = path.join(extractDir, 'install.command')
  try {
    await fs.access(direct)
    return direct
  } catch {}
  const entries = await fs.readdir(extractDir, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const nested = path.join(extractDir, entry.name, 'install.command')
    try {
      await fs.access(nested)
      return nested
    } catch {}
  }
  return null
}

async function downloadAndInstall(mainWindow, data) {
  if (!validateDownloadUrl(data.downloadUrl)) {
    throw new Error('更新地址不是安全的 HTTPS 链接')
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sticker-maker-update-'))
  const zipPath = path.join(tempDir, 'update.zip')
  mainWindow?.setProgressBar(0.15)
  const response = await fetch(data.downloadUrl, { cache: 'no-store' })
  if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
  const bytes = Buffer.from(await response.arrayBuffer())
  await fs.writeFile(zipPath, bytes)
  if (!(await verifyChecksum(zipPath, data.sha256))) {
    throw new Error('更新包校验失败，已停止安装')
  }

  const extractDir = path.join(tempDir, 'unpacked')
  await fs.mkdir(extractDir)
  mainWindow?.setProgressBar(0.65)
  await execFileAsync('/usr/bin/ditto', ['-x', '-k', zipPath, extractDir])
  const installer = await findInstaller(extractDir)
  if (!installer) throw new Error('更新包内没有找到 install.command')
  const appBundle = path.join(path.dirname(installer), `${PRODUCT_NAME}.app`)
  try {
    await fs.access(appBundle)
  } catch {
    throw new Error(`更新包内没有找到「${PRODUCT_NAME}.app」`)
  }
  await fs.chmod(installer, 0o755)
  mainWindow?.setProgressBar(1)
  spawn('/bin/bash', [installer, '--update'], {
    detached: true,
    stdio: 'ignore',
  }).unref()
  app.quit()
}

async function checkForUpdates(mainWindow, { manual = false } = {}) {
  try {
    const currentVersion = require('../../package.json').version
    const response = await fetch(VERSION_CHECK_URL, { cache: 'no-store' })
    if (!response.ok) throw new Error(`版本服务返回 HTTP ${response.status}`)
    const data = await response.json()
    if (!data.version || !isNewerVersion(data.version, currentVersion)) {
      if (manual) {
        await dialog.showMessageBox(mainWindow, {
          type: 'info',
          title: '已是最新版本',
          message: `当前版本 ${currentVersion} 已是最新版本。`,
        })
      }
      return { updateAvailable: false, currentVersion }
    }

    const choice = await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: '发现新版本',
      message: `新版本 ${data.version} 可用（当前 ${currentVersion}）`,
      detail: data.releaseNotes || '',
      buttons: ['一键更新', '打开下载页', '稍后'],
      defaultId: 0,
      cancelId: 2,
    })
    if (choice.response === 0) {
      await downloadAndInstall(mainWindow, data)
    } else if (choice.response === 1 && validateDownloadUrl(data.downloadUrl)) {
      await shell.openExternal(data.downloadUrl)
    }
    return { updateAvailable: true, version: data.version }
  } catch (error) {
    mainWindow?.setProgressBar(-1)
    if (manual) {
      await dialog.showMessageBox(mainWindow, {
        type: 'error',
        title: '检查更新失败',
        message: error.message || String(error),
        detail: '请检查网络连接，或稍后从介绍页手动下载。',
      })
    }
    console.error('[updater] 检查失败', error)
    return { updateAvailable: false, error: error.message || String(error) }
  }
}

module.exports = {
  checkForUpdates,
  downloadAndInstall,
  isNewerVersion,
  validateDownloadUrl,
  verifyChecksum,
}
