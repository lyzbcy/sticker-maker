// Download bounded waves of GPT-planned GIF sheets; no image synthesis via API.
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {Bridge,json,sleep}=require('../../lyzbcy-sticker-publisher/scripts/web_bridge.cjs');
const {cleanupCompletedTabs}=require('./web_tab_lifecycle.cjs');
function validatePlan(m){
  if(!Array.isArray(m.sheetPlans)||!m.sheetPlans.length||m.sheetPlans.length>8||new Set(m.sheetPlans.map(s=>s.index)).size!==m.sheetPlans.length)throw Error('Supply 1–8 distinct sheetPlans for one album');
  if(m.sheetPlans.some(s=>!Number.isInteger(s.index)||s.index<0||typeof s.prompt!=='string'))throw Error('Invalid sheet plan');
  if(new Set((m.sheets||[]).map(s=>s.index)).size!==(m.sheets||[]).length||(m.sheets||[]).some(s=>!m.sheetPlans.some(p=>p.index===s.index)))throw Error('Saved sheets must match the unique original plan');
  if(!m.outputDir||!m.logDir||!m.base||!m.guide)throw Error('Require outputDir, logDir, base and guide');
  if((m.sheets||[]).some(s=>s.sendIntentAt&&!s.sentAt))throw Error('Unknown send outcome: reconcile original conversation before resuming');
}
async function run(file){
  const m=JSON.parse(await fs.readFile(file,'utf8'));validatePlan(m);
  m.sheets=m.sheets||[];m.startedAt=m.startedAt||Date.now();m.session=m.session||'sticker-gif-'+m.startedAt;
  await fs.mkdir(m.logDir,{recursive:true});await fs.mkdir(path.join(m.outputDir,'原图'),{recursive:true});
  const save=()=>json(file,m),log=async(event,data={})=>{
    await fs.appendFile(path.join(m.logDir,'events.jsonl'),JSON.stringify({at:new Date().toISOString(),event,...data})+'\n');
    if(event!=='bridge')console.log(JSON.stringify({event,...data}));
  };
  const b=new Bridge({session:m.session,log}),cleanup=()=>cleanupCompletedTabs(b,{albums:m.sheets},{save,log});
  await save();await cleanup();
  async function send(plan){
    const prompt=await fs.readFile(path.resolve(m.outputDir,plan.prompt),'utf8');
    const t=await b.call('navigate',{url:'https://chatgpt.com/',newTab:true,group_title:'动态表情批次'});
    const item={index:plan.index,tabId:t.tabId,createdByWorkflow:true,dir:m.outputDir,prompt:plan.prompt};m.sheets.push(item);await save();
    await b.call('cdp',{method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});
    let scope;
    for(let i=0;i<100;i++){
      scope=await b.eval(`document.querySelector('form[data-composer-placement="thread"] [contenteditable=true]')?'form[data-composer-placement="thread"]':document.querySelector('form[data-composer-placement="home"] [contenteditable=true]')?'form[data-composer-placement="home"]':null`);
      if(scope)break;await sleep(200);
    }
    if(!scope)throw Error('ChatGPT composer unavailable; no prompt sent');
    await b.call('upload',{selector:scope+' input[type=file][accept="image/*"][multiple]',files:[m.base,m.guide]});
    await b.call('fill',{selector:scope+' [contenteditable=true]',value:prompt});
    let ready=false;
    for(let i=0;i<160;i++){
      ready=await b.eval(`(()=>{const f=document.querySelector(${JSON.stringify(scope)}),b=f?.querySelector('button[aria-label="发送"],button[data-testid="send-button"]');return !!b&&!b.disabled&&!f.querySelector('[role=progressbar]')&&f.querySelectorAll('[data-composer-attachments] img').length===2})()`);
      if(ready)break;await sleep(250);
    }
    if(!ready)throw Error('Attachments unavailable; unsent tab retained');
    item.sendIntentAt=Date.now();await save();
    await b.call('click',{selector:scope+' button[aria-label="发送"],'+scope+' button[data-testid="send-button"]'});
    item.sentAt=Date.now();await save();await log('prompt_sent',{index:item.index,tabId:item.tabId});
  }
  while(m.sheets.filter(s=>s.file).length<m.sheetPlans.length){
    // Unsent entries require explicit reconciliation rather than silently opening duplicates.
    if(m.sheets.some(s=>!s.file&&!s.sentAt))throw Error('Unsent tab retained; reconcile before continuing');
    let pending=m.sheets.filter(s=>!s.file);
    for(const plan of m.sheetPlans){
      if(pending.length>=2)break;
      if(!m.sheets.some(s=>s.index===plan.index)){await send(plan);pending=m.sheets.filter(s=>!s.file);}
    }
    for(const item of pending){
      await b.attach(item.tabId);
      const info=await b.read(`({url:location.href,image:[...document.images].some(i=>i.alt==='已生成图像 1'&&Math.min(i.naturalWidth,i.naturalHeight)>=256&&Math.max(i.naturalWidth,i.naturalHeight)>=800)})`);
      if(!info.image){if(Date.now()-item.sentAt>480000)throw Error('Generation unresolved: original page retained; do not resend');continue;}
      const key='__gifSheetDownload'+item.index;
      await b.job(key,`const im=[...document.images].find(i=>i.alt==='已生成图像 1');const blob=await(await fetch(im.src)).blob();return await new Promise(r=>{const f=new FileReader;f.onload=()=>r(f.result);f.readAsDataURL(blob)})`);
      const data=(await b.wait(key,{timeout:20000,interval:200})).result;
      const raw=Buffer.from(data.split(',')[1],'base64');const response=await b.eval('document.body.innerText');
      item.sourceFile='原图/sheet-'+item.index+'.png';item.sourceProofFile='原图/source-'+item.index+'.json';item.responseFile='原图/response-'+item.index+'.json';
      const sha256=crypto.createHash('sha256').update(raw).digest('hex');
      await fs.writeFile(path.join(m.outputDir,item.sourceFile),raw);
      await json(path.join(m.outputDir,item.sourceProofFile),{sha256,conversationUrl:info.url});
      await json(path.join(m.outputDir,item.responseFile),{url:info.url,text:response});
      Object.assign(item,{file:item.sourceFile,sha256,conversationUrl:info.url,downloadedAt:Date.now()});
      await save();await log('sheet_downloaded',{index:item.index,sha256});
      await cleanup();
    }
    if(m.sheets.some(s=>!s.file))await sleep(1800);
  }
  await log('generation_complete',{sheets:m.sheets.length,elapsedMs:Date.now()-m.startedAt});
}
if(require.main===module){
  if(process.argv.includes('--help'))console.log('node web_gif_generate.cjs <manifest.json>; requires outputDir/logDir/base/guide/sheetPlans[{index,prompt}]; at most two live generation tabs, no retry on unknown send.');
  else if(!process.argv[2]){console.error('Manifest required');process.exitCode=1;}
  else run(path.resolve(process.argv[2])).catch(e=>{console.error(String(e));process.exitCode=1;});
}
module.exports={validatePlan};
