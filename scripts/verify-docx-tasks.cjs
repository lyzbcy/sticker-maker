// Real packaged UI and IPC against isolated local data; never sends feedback.
const fs = require('fs'), path = require('path'), assert = require('assert'), crypto = require('crypto'), os = require('os')
const { _electron } = require(process.env.STICKER_QA_PLAYWRIGHT || '../sticker_engine/.venv/Lib/site-packages/playwright/driver/package')
const repo=path.resolve(__dirname,'..'), evidence=process.env.STICKER_QA_EVIDENCE || path.join(repo,'verification/docx-tasks-20261021')
fs.mkdirSync(evidence,{recursive:true})
const task=path.join(process.platform==='win32'?'C:/sm-qa':os.tmpdir(),'doc-ui-'+crypto.randomBytes(3).toString('hex'))
fs.mkdirSync(task,{recursive:true})
const executable=process.env.STICKER_QA_APP || path.join(process.env.LOCALAPPDATA,'StickerMakerBuilds/0.6.2/desktop-release/win-unpacked/表情包一键制作.exe')
const env={...process.env,STICKER_ENGINE_USER_DATA:path.join(task,'engine'),STICKER_DESKTOP_USER_DATA:path.join(task,'desktop'),STICKER_ENGINE_NO_LOCK:'1',STICKER_DESKTOP_HIDE_WINDOW:'1',PYTHON_KEYRING_BACKEND:'keyring.backends.null.Keyring'}
delete env.ELECTRON_RUN_AS_NODE
const report={fixture:task,app:executable,real_data_modified:false,feedback_sent:false}
async function launch(){
 const app=await _electron.launch({executablePath:executable,env,timeout:30000}), page=await app.firstWindow()
 await page.locator('[data-test=workspace-tabs]').waitFor()
 return {app,page}
}
async function send(page,cmd,args={}){const result=await page.evaluate(async v=>window.api.send(...v),[cmd,args]);assert.equal(result.status,'ok',JSON.stringify(result));return result.data}
;(async()=>{
 let session
 try{
  session=await launch();let {app,page}=session
  report.version=(await send(page,'get_version')).version;assert.equal(report.version,'0.6.2')
  report.packaged=await app.evaluate(({app})=>app.isPackaged)
  assert(!fs.existsSync(path.join(path.dirname(executable),'resources/sticker-engine-cli/_internal/browsers')))
  report.browser_runtime=await send(page,'browser_runtime_status');assert(report.browser_runtime.ready)
  report.blank_browser_check=await send(page,'runtime_check');assert(report.blank_browser_check.frozen)
  await page.setViewportSize({width:800,height:600})
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('.main')).opacity==='1')
  await page.screenshot({path:path.join(evidence,'home-800.png')})
  for(let step=0;step<5;step++){
   await page.getByRole('button',{name:'可选使用教程',exact:true}).click()
   for(let i=0;i<step;i++)await page.getByRole('button',{name:'下一步',exact:true}).click()
   await page.locator('[data-test=exit-tutorial]').click()
   await page.locator('[data-test=workspace-tabs]').waitFor()
  }
  report.tutorial_exit_all_five_steps=true
  await page.locator('[data-test=tab-allStickers]').click()
  await page.getByRole('heading',{name:/全部表情/}).waitFor()
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('.all-stickers')).opacity==='1')
  await page.screenshot({path:path.join(evidence,'all-stickers-800.png')})
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))
  await page.locator('[data-test=tab-health]').click()
  await page.locator('[data-test=health-panel]').waitFor()
  await page.getByRole('button',{name:'重新检查',exact:true}).waitFor({timeout:30000})
  await page.locator('[data-test=debug-mode]').check()
  await page.waitForFunction(()=>document.querySelector('[data-test=health-panel]')?.textContent.includes('已开启详细排障日志'))
  await page.evaluate(()=>window.api.recordActivity({stage:'qa',message:'QA_PERSISTED_CONTEXT token=fixture-private-token'}))
  let diagnostic=await page.evaluate(()=>window.api.diagnosticSnapshot())
  assert(diagnostic.debug);assert(diagnostic.text.includes('QA_PERSISTED_CONTEXT'));assert(!diagnostic.text.includes('fixture-private-token'))
  await page.evaluate(()=>window.scrollTo(0,0))
  await page.screenshot({path:path.join(evidence,'health-800.png')})
  await page.locator('[data-test=debug-mode]').scrollIntoViewIfNeeded()
  await page.screenshot({path:path.join(evidence,'diagnostics-800.png')})
  assert(await page.locator('[data-test=workspace-tabs]').isVisible())
  const tabBox=await page.locator('[data-test=workspace-tabs]').boundingBox()
  assert(tabBox.y>=0 && tabBox.y<100)
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))
  const exported=path.join(task,'exported.jsonl')
  await app.evaluate(({dialog},filename)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:filename})},exported)
  await page.getByRole('button',{name:'导出完整诊断日志',exact:true}).click()
  await page.getByText('已导出脱敏日志',{exact:true}).waitFor()
  const exportedText=fs.readFileSync(exported,'utf8')
  assert(!exportedText.includes('fixture-private-token'));assert(exportedText.includes('QA_PERSISTED_CONTEXT'))
  exportedText.split('\n').filter(Boolean).forEach(line=>JSON.parse(line))
  report.diagnostics_export_redacted=true
  await page.getByRole('button',{name:'反馈问题',exact:true}).click()
  await page.getByRole('heading',{name:'遇到问题反馈',exact:true}).waitFor()
  await page.waitForFunction(()=>document.querySelector('pre')?.textContent.includes('QA_PERSISTED_CONTEXT'))
  const preview=await page.locator('pre').textContent()
  assert(!preview.includes('fixture-private-token'))
  report.feedback_preview_uses_local_logs=true
  await page.evaluate(()=>window.api.recordActivity({stage:'qa',message:'QA_NORMAL_EXIT_BUFFERED'}))
  if(process.platform==='darwin') {
   await app.close();report.mac_normal_quit_flushes_cleanly=true
  } else {
   const closed=new Promise(resolve=>app.process().once('exit',code=>resolve(code)))
   await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].close())
   assert.equal(await closed,0);report.window_close_flushes_cleanly=true
  }
  session=null
  session=await launch();diagnostic=await session.page.evaluate(()=>window.api.diagnosticSnapshot())
  assert(diagnostic.text.includes('QA_NORMAL_EXIT_BUFFERED'));assert(diagnostic.debug)
  await session.page.evaluate(()=>window.api.diagnosticMode(false))
  report.restart_preserves_context_and_mode=true
  report.all_stickers_tab_one_click=true;report.warning_actions_visible=true;report.horizontal_overflow=false
  fs.writeFileSync(path.join(evidence,'electron-acceptance.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report,null,2))
 }finally{if(session)await session.app.close()}
})().catch(error=>{console.error(error);process.exitCode=1})
