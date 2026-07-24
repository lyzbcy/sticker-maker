// electron-builder afterPack 钩子：给 sticker-engine-cli 做 ad-hoc 签名
// 解决未签名 Mach-O 在 .app bundle 内被 macOS 静默杀掉的问题
const { execSync } = require('child_process')
const path = require('path')

exports.afterPack = async function (context) {
  if (context.electronPlatformName !== 'darwin') return
  // appOutDir 是 release/mac-arm64，.app 在其下（productName 命名）
  const appName = context.packager.appInfo.productFilename
  // onedir 模式：cli 可执行在 Resources/sticker-engine-cli/sticker-engine-cli
  const cliPath = path.join(context.appOutDir, appName + '.app', 'Contents', 'Resources', 'sticker-engine-cli', 'sticker-engine-cli')
  try {
    execSync(`codesign --force --sign - "${cliPath}"`, { stdio: 'inherit' })
    console.log(`[afterPack] sticker-engine-cli 已 ad-hoc 签名: ${cliPath}`)
  } catch (e) {
    console.error(`[afterPack] 签名失败:`, e.message)
  }
}
