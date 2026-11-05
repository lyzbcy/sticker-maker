// Three explicit phases: begin -> reviewed assets -> approved publish. No model-boundary pauses inside phases.
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {execFile}=require('node:child_process');
const {Bridge,json,sleep}=require('../../lyzbcy-sticker-publisher/scripts/web_bridge.cjs');
const {meaning,publish}=require('../../lyzbcy-sticker-publisher/scripts/web_sdk_publish.cjs');
const HERE=__dirname,ROOT=path.resolve(HERE,'../../../..');
async function py(script,...args){return new Promise((res,rej)=>execFile('python',['-X','utf8',path.join(HERE,script),...args.map(String)],{encoding:'utf8',maxBuffer:5e6,windowsHide:true},(e,o,err)=>e?rej(Error(err+' '+o)):res(o)));}
async function load(p){return JSON.parse(await fs.readFile(p,'utf8'));}
function prompt(a){return `请直接生成一张微信表情包原图。附件为唯一原创角色${a.characters.join('+')}，严格保持各自脸、发型、服装、配饰、材质。主题：${a.theme}。使用场景：${a.scenario}。人群：${a.audience}。自由设计16张不同、可独立发送的实用聊天表情，动作与1—4字中文文案由你发挥，不编连续故事。正方形4×4均匀十六宫格，正好16格，完整留空不跨格；人物和文字外围有干净连续白描边。背景全图纯洋红#ff00ff，无渐变纹理、地面投影、网格线框、编号、水印；角色正常颜色无洋红反光。文案与人物保持间隔。生成后在同一回复附JSON数组index、text、meaning，含义仅1—4个汉字，不含标点。直接开始生图，不为JSON另生成图。`;}
async function begin(config,manifestFile,log,bridge){
  const tabs=(await bridge.call('list_browser_tabs')).tabs;
  let platform=tabs.find(t=>t.url.includes('/mmemoticonwebnode-bin/pages/stickerPage/detail'))||tabs.find(t=>t.url.startsWith('https://sticker.weixin.qq.com/'));
  if(!platform)throw Error('Open the logged-in WeChat platform before starting');
  await bridge.attach(platform.tabId);await bridge.call('cdp',{method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});await bridge.job('__stickerList',`return await(await fetch('/cgi-bin/mmemoticon-bin/home?lang=zh_CN&f=json')).json();`);
  const list=(await bridge.wait('__stickerList',{timeout:20000,interval:200})).result;
  if(list.base_resp?.ret!==0||!Array.isArray(list.List))throw Error('WeChat login required');
  if(config.accountAnchor&&!list.List.some(x=>x.StikerID===config.accountAnchor))throw Error('Wrong WeChat account');
  if(!platform.url.includes('/mmemoticonwebnode-bin/pages/stickerPage/detail')){
    platform=await bridge.call('navigate',{url:'https://sticker.weixin.qq.com/cgi-bin/mmemoticonwebnode-bin/pages/stickerPage/detail',newTab:true,group_title:'两弹表情包提效复测'});
  }
  const max=Math.max(0,...list.List.filter(x=>/^周三涵做表情\d+$/.test(x.Name)).map(x=>+x.Name.match(/\d+$/)[0]));
  const evidence=path.join(config.logDir,'platform-check.json');
  await json(evidence,{max_episode:max,source_url:platform.url,checked_at:new Date().toISOString(),verification_note:'完整List含草稿待审，核对已知账号作品ID'});
  const sourceCommit=(await new Promise((res,rej)=>execFile('git',['rev-parse','HEAD'],{cwd:ROOT,encoding:'utf8'},(e,o)=>e?rej(e):res(o)))).trim();
  const m={sourceCommit,logDir:config.logDir,startedAt:Date.now(),platformTabId:platform.tabId,albums:[]};
  // Caller start is before login/list, so preparation cannot disappear from the benchmark.
  m.startedAt=config.startedAt;
  for(let i=0;i<2;i++){
    const n=max+i+1,o=JSON.parse(await py('web_prepare.py','--output-root',config.outputRoot,'--assets-root',config.assetsRoot,'--evidence',evidence,'--episode',n));
    const s=await load(path.join(o.output_dir,'prep_state.json'));
    m.albums.push({episode:n,name:s.episode_name,dir:o.output_dir,characters:s.characters,role:s.characters.length===2?'人物合辑':s.characters[0]==='捞鱼'?'男人':'女人',bases:s.bases,...config.themes[i]});
  }
  await json(manifestFile,m);await log('prepared',{max,albums:m.albums.map(a=>({name:a.name,characters:a.characters}))});
  for(const a of m.albums){
    a.sendStarted=Date.now();const t=await bridge.call('navigate',{url:'https://chatgpt.com/',newTab:true,group_title:'两弹表情包提效复测'});a.tabId=t.tabId;
    await bridge.call('cdp',{method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});
    let ready=false;
    for(let i=0;i<50;i++){if(await bridge.eval(`!!document.querySelector('input[type=file][accept="image/*"][multiple]')&&!!document.querySelector('[contenteditable="true"]')`)){ready=true;break;}await sleep(200);}
    if(!ready)throw Error('ChatGPT login/composer not ready');
    a.prompt=prompt(a);await fs.writeFile(path.join(a.dir,'生图提示词.txt'),a.prompt);
    await bridge.call('upload',{selector:'input[type=file][accept="image/*"][multiple]',files:a.bases.map(b=>path.join(a.dir,b.path))});
    await bridge.call('fill',{selector:'[contenteditable="true"]',value:a.prompt});
    let sent=false;
    for(let i=0;i<80;i++){
      const usable=await bridge.eval(`(()=>{const b=document.querySelector('button[aria-label="发送"],button[data-testid="send-button"]');return !!b&&!b.disabled&&!document.querySelector('[role="progressbar"]')})()`);
      if(usable){await bridge.call('click',{selector:'button[aria-label="发送"],button[data-testid="send-button"]'});a.sentAt=Date.now();sent=true;break;}
      await sleep(250);
    }
    if(!sent)throw Error('Attachment/send not ready; prompt not resent');
    await log('prompt_sent',{episode:a.episode,send_ms:a.sentAt-a.sendStarted});await json(manifestFile,m);
  }
  const pending=new Set(m.albums.map(a=>a.episode));const deadline=Date.now()+360000;
  while(pending.size&&Date.now()<deadline){
    for(const a of m.albums.filter(x=>pending.has(x.episode))){
      await bridge.attach(a.tabId);
      const info=await bridge.read(`({url:location.href,image:[...document.images].filter(x=>x.alt==='已生成图像 1'&&x.naturalWidth>=800).map(x=>({w:x.naturalWidth,h:x.naturalHeight}))[0]})`);
      a.conversationUrl=info.url;
      if(!info.image)continue;
      a.imageReadyAt=Date.now();await log('image_ready',{episode:a.episode,generation_observed_ms:a.imageReadyAt-a.sentAt,...info.image});
      const key='__stickerDownload';await bridge.job(key,`const im=[...document.images].find(x=>x.alt==='已生成图像 1'&&x.naturalWidth>=800);const blob=await(await fetch(im.src)).blob();return await new Promise(resolve=>{const reader=new FileReader;reader.onload=()=>resolve({data:reader.result,type:blob.type,size:blob.size});reader.readAsDataURL(blob)});`);
      const downloaded=(await bridge.wait(key,{timeout:20000,interval:150})).result;
      const raw=Buffer.from(downloaded.data.split(',')[1],'base64');await fs.writeFile(path.join(a.dir,'原图/grid_4x4.png'),raw);
      await json(path.join(a.dir,'原图/generation-source.json'),{conversationUrl:a.conversationUrl,sha256:crypto.createHash('sha256').update(raw).digest('hex'),mime:downloaded.type,imageReadyAt:a.imageReadyAt});
      const provisional=path.join(a.dir,'meanings.json');await json(provisional,Object.fromEntries(Array.from({length:16},(_,i)=>[String(i+1),String(i+1).padStart(2,'0')])));
      const start=Date.now();const output=await py('web_process_grid.py','--episode-dir',a.dir,'--meanings',provisional,'--outline-px',2);a.processMs=Date.now()-start;
      await log('grid_processed',{episode:a.episode,process_ms:a.processMs,result:JSON.parse(output)});pending.delete(a.episode);await json(manifestFile,m);
    }
    if(pending.size)await sleep(1800);
  }
  if(pending.size)throw Error('Generation not complete; original request retained, do not resend');
  const board=(await py('web_batch_local.py','board','--manifest',manifestFile)).trim();
  m.reviewStartedAt=Date.now();await json(manifestFile,m);await log('combined_review_ready',{board});return {manifest:manifestFile,board};
}
async function main(){
  const [command,...argv]=process.argv.slice(2);
  if(!command||argv.includes('--help')||command==='--help'){console.log(JSON.stringify({ok:true,data:{usage:'node web_batch.cjs begin --config config.json | assets --manifest manifest.json --review review.json | publish --manifest manifest.json --approval approval.json',options:['--daemon-url URL'],note:'All paths use the existing skills/repo. No generation or submission retry on unknown outcomes.'}}));return;}
  const opts={};for(let i=0;i<argv.length;i+=2)opts[argv[i].replace(/^--/,'')]=argv[i+1];
  let m,config,manifestFile=opts.manifest;
  if(command==='begin'){config=await load(opts.config);config.startedAt=Date.now();manifestFile=path.join(config.logDir,'manifest.json');await fs.mkdir(config.logDir,{recursive:true});try{await fs.access(manifestFile);throw Error('Manifest exists; resume instead of generating again');}catch(e){if(e.code!=='ENOENT')throw e;}}
  else m=await load(manifestFile);
  const logDir=config?.logDir||m.logDir;const log=async(event,data={})=>{await fs.appendFile(path.join(logDir,'events.jsonl'),JSON.stringify({at:new Date().toISOString(),event,...data})+'\n');if(event!=='bridge'){const {payload,response,...short}=data;console.log(JSON.stringify({ok:true,data:{event,...short,...(response?{businessRet:response.data?.baseResp?.ret}:{})}}));}};
  const bridge=new Bridge({url:opts['daemon-url'],log});let result;
  if(command==='begin'){await log('batch_started',{startedAt:config.startedAt});result=await begin(config,manifestFile,log,bridge);}
  else if(command==='assets'){
    const review=await load(opts.review);
    for(const a of review.albums)a.meanings=a.meanings.map(meaning);
    const clean=path.join(logDir,'review.json');await json(clean,review);
    await log('combined_review_completed',{review_ms:Date.now()-m.reviewStartedAt});
    result={board:(await py('web_batch_local.py','assets','--manifest',manifestFile,'--review',clean)).trim()};await log('assets_ready',result);
  }else if(command==='publish'){
    const approval=await load(opts.approval);
    for(const a of m.albums){const r=await load(path.join(a.dir,'发布素材清单.json'));const hashes=Object.fromEntries(r.files.map(x=>[x.path,x.sha256]));const app=approval.albums.find(x=>x.episode===a.episode);
      if(!app?.approved||!(app.portrait_reviewed||app.head_only)||JSON.stringify(app.asset_hashes)!==JSON.stringify(hashes))throw Error('Visual approval must match CURRENT five asset hashes');
      await json(path.join(a.dir,'发布素材复核.json'),{...app,role:a.role,human_score:null});
      const pf=await new Promise((res,rej)=>execFile('python',['-X','utf8',path.join(HERE,'../../lyzbcy-sticker-publisher/scripts/web_preflight.py'),'--episode-dir',a.dir,'--role',a.role],{encoding:'utf8',windowsHide:true},(e,o,err)=>e?rej(Error(err+' '+o)):res(o)));await log('preflight_passed',{name:a.name,result:JSON.parse(pf)});
    }
    const start=Date.now();await log('api_publish_started');const state=await publish(bridge,m,{log});
    await json(path.join(logDir,'receipts.json'),state.result);const metrics={started_at:new Date(m.startedAt).toISOString(),verified_at:new Date(state.endedAt).toISOString(),end_to_end_ms:state.endedAt-m.startedAt,publish_ms:state.endedAt-start,albums:m.albums.map(a=>({episode:a.episode,send_ms:a.sentAt-a.sendStarted,generation_observed_ms:a.imageReadyAt-a.sentAt,process_ms:a.processMs})),goal_ms:300000,met_goal:state.endedAt-m.startedAt<=300000};
    await json(path.join(logDir,'timings.json'),metrics);await fs.writeFile(path.join(logDir,'report.md'),'# 两弹优化实测\n\n'+JSON.stringify(metrics,null,2)+'\n\n'+JSON.stringify(state.result,null,2)+'\n\n从查号前开始到最终唯一名称回读，含审图/脚本/编排等待；生图为首次加载观测时间，含轮询间隔。待审核不等于已上架。原始日志events.jsonl及sdk-journal.json。\n');
    await py('web_batch_local.py','archive','--manifest',manifestFile);await log('batch_verified',{...metrics,receipts:state.result});result=metrics;
  }else throw Error('Unknown command '+command);
  console.log(JSON.stringify({ok:true,data:result}));
}
if(require.main===module)main().catch(e=>{console.error(JSON.stringify({ok:false,error:{code:'WORKFLOW_STOPPED',message:String(e)}}));process.exitCode=1;});
module.exports={prompt};
