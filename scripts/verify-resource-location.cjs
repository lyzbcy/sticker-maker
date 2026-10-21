const fs = require('fs'), path = require('path'), assert = require('assert')
const { _electron } = require('../sticker_engine/.venv/Lib/site-packages/playwright/driver/package')
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const appPath = path.join(process.env.LOCALAPPDATA, 'StickerMakerBuilds/0.6.1/desktop-release/win-unpacked/表情包一键制作.exe')
const evidence = path.resolve('verification/resource-location-20261021')
const report = { app: appPath }
async function launch(profile) {
  const env = { ...process.env, STICKER_ENGINE_USER_DATA: path.join(fixture.task, profile+'-engine'),
    STICKER_DESKTOP_USER_DATA: path.join(fixture.task, profile+'-desktop'), STICKER_DESKTOP_HIDE_WINDOW: '1', STICKER_ENGINE_NO_LOCK: '1' }
  delete env.ELECTRON_RUN_AS_NODE
  const app = await _electron.launch({ executablePath: appPath, env, timeout: 30000 })
  const page = await app.firstWindow()
  await page.waitForFunction(() => window.api && document.querySelector('#app')?.__vue_app__)
  return { app, page }
}
async function send(page, cmd, args = {}) {
  const result = await page.evaluate(async ([cmd,args]) => window.api.send(cmd,args), [cmd,args])
  assert.equal(result.status, 'ok', JSON.stringify(result))
  return result.data
}
async function select(app, page, folder) {
  await app.evaluate(({ dialog }, folder) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] })
  }, folder)
  await page.locator('[data-test=choose-resource-location]').click()
  await page.locator('[data-test=location-candidate]').waitFor()
}
async function settings(page) {
  await page.evaluate(() => {
    const store = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('engine')
    store.settingsTab = 'resource'; store.phase = 'settings'
  })
  await page.locator('[data-test=resource-location]').waitFor()
}
;(async () => {
  let session
  try {
    session = await launch('direct')
    const { app, page } = session
    report.version = (await send(page, 'get_version')).version
    assert.equal(report.version, '0.6.1')
    report.packaged = await app.evaluate(({ app }) => app.isPackaged)
    await page.locator('[data-test=choose-resource-location]').waitFor()
    await page.screenshot({ path: path.join(evidence, 'empty-home.png') })
    await select(app, page, fixture.parent)
    assert.equal(await page.locator('[data-test=location-candidate] option').count(), 2)
    await page.locator('[data-test=location-candidate]').selectOption(fixture.collection)
    assert(await page.locator('[data-test=connect-resource-location]').isDisabled())
    await page.setViewportSize({ width: 800, height: 600 })
    await page.screenshot({ path: path.join(evidence, 'choose-location-800.png') })
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    await page.locator('[data-test=location-confirm]').check()
    await page.locator('[data-test=connect-resource-location]').click()
    await page.waitForFunction(() => !document.querySelector('[data-test=resource-location]'))
    const rows = (await send(page, 'list_episodes')).episodes
    assert.equal(rows.length, 1); assert.equal(rows[0].platform_item_id, 'original-platform-id')
    await settings(page)
    assert((await page.locator('[data-test=resource-location]').innerText()).includes(fixture.collection))
    await page.screenshot({ path: path.join(evidence, 'connected-settings-800.png') })
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    report.parent_discovery = 2; report.direct_connect = true; report.horizontal_overflow = false
    await app.close(); session = null
    session = await launch('direct')
    const status = await send(session.page, 'library_status')
    assert.equal(status.root, fixture.collection); assert.equal(status.storage_mode, 'projects')
    assert.equal((await send(session.page, 'list_episodes')).episodes.length, 1)
    report.restart_remembers_location = true
    await session.app.close(); session = null
    session = await launch('legacy')
    await select(session.app, session.page, fixture.legacy)
    await session.page.locator('[data-test=location-confirm]').check()
    await session.page.locator('[data-test=connect-resource-location]').click()
    await session.page.waitForFunction(() => !document.querySelector('[data-test=resource-location]'))
    assert.equal((await send(session.page, 'list_episodes')).episodes[0].platform_item_id, 'original-platform-id')
    report.legacy_connect_from_unbound_device = true
    fs.writeFileSync(path.join(fixture.task, 'report.json'), JSON.stringify(report, null, 2))
  } finally { if (session) await session.app.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
