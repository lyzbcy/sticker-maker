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

/**
 * 按平台选择更新资产。
 * 新 schema：platforms.{mac,win}.{url,sha256}；旧 schema（v0.2.0 Mac 客户端）：
 * downloadUrl/sha256 即 Mac 包。旧客户端读不到 platforms 字段，直接用顶层字段，互不影响。
 */
function pickUpdateAsset(data, platform) {
  const key = platform === 'win32' ? 'win' : 'mac'
  const fromPlatforms = data && data.platforms && data.platforms[key]
  if (fromPlatforms && fromPlatforms.url) {
    return { url: fromPlatforms.url, sha256: fromPlatforms.sha256 || '' }
  }
  if (key === 'mac' && data && data.downloadUrl) {
    return { url: data.downloadUrl, sha256: data.sha256 || '' }
  }
  return null
}

async function downloadToFile(url, destPath) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
  const bytes = Buffer.from(await response.arrayBuffer())
  await fs.writeFile(destPath, bytes)
  return bytes.length
}

async function downloadAndInstall(mainWindow, data) {
  const asset = pickUpdateAsset(data, process.platform)
  if (!asset) {
    throw new Error('版本信息里没有当前平台的更新包')
  }
  if (!validateDownloadUrl(asset.url)) {
    throw new Error('更新地址不是安全的 HTTPS 链接')
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sticker-maker-update-'))
  mainWindow?.setProgressBar(0.15)

  if (process.platform === 'win32') {
    // Windows：下载 NSIS 安装器 → sha256 校验 → 静默安装（/S）→ 退出
    const installerPath = path.join(tempDir, 'update-setup.exe')
    await downloadToFile(asset.url, installerPath)
    if (!(await verifyChecksum(installerPath, asset.sha256))) {
      throw new Error('更新包校验失败，已停止安装')
    }
    mainWindow?.setProgressBar(1)
    spawn(installerPath, ['/S'], {
      detached: true,
      stdio: 'ignore',
    }).unref()
    app.quit()
    return
  }

  // macOS：下载 zip → 解包 → install.command --update
  const zipPath = path.join(tempDir, 'update.zip')
  await downloadToFile(asset.url, zipPath)
  if (!(await verifyChecksum(zipPath, asset.sha256))) {
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
    const asset = pickUpdateAsset(data, process.platform)
    if (choice.response === 0) {
      await downloadAndInstall(mainWindow, data)
    } else if (choice.response === 1 && asset && validateDownloadUrl(asset.url)) {
      await shell.openExternal(asset.url)
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
  pickUpdateAsset,
  validateDownloadUrl,
  verifyChecksum,
}
