// Observed and exercised contract: 613/614, 2026-11-05. Reuse current page SDK.
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {json}=require('./web_bridge.cjs');
function meaning(text) {
  const value=text.normalize('NFKC').replace(/[\p{P}\p{S}\s]/gu,'');
  if(!/^[\p{Script=Han}]{1,4}$/u.test(value))throw Error('Review a 1–4 Han-character platform meaning: '+text);
  return value;
}
async function inputs(album) {
  const root=album.dir;
  const manifest=JSON.parse(await fs.readFile(path.join(root,'成品清单.json'),'utf8'));
  const proof=JSON.parse(await fs.readFile(path.join(root,'头像裁切.json'),'utf8'));
  if(proof.origin!=='current_album_sticker')throw Error('Head must come from this album sticker');
  const names=manifest.files.map(x=>meaning(x.meaning));
  if(manifest.files.length!==16 || new Set(names).size!==16)throw Error('16 distinct reviewed meanings required');
  const make=async f=>{const b=await fs.readFile(path.join(root,f));return {name:path.basename(f),data:b.toString('base64'),md5:crypto.createHash('md5').update(b).digest('hex')};};
  return {...album,description:(await fs.readFile(path.join(root,'介绍.txt'),'utf8')).trim(),
    assets:await Promise.all(['横幅/横幅.png','封面/封面.png','图标/图标.png','赞赏图/赞赏引导图.png','赞赏图/赞赏致谢图.png'].map(make)),
    emojis:await Promise.all(manifest.files.map(async(x,i)=>({...await make(x.file),index:i+1,meaning:names[i]})))};
}
function browserPublish(albums, jobKey) {
  return `const data=${JSON.stringify(albums)};const state=window[${JSON.stringify(jobKey)}];state.events=[];state.ack=0;
  let seq=0;
  const checkpoint=async(event,info={})=>{const item={seq:++seq,at:Date.now(),event,...info};state.events.push(item);const start=Date.now();while(state.ack<item.seq){if(Date.now()-start>15000)throw Error('Host journal acknowledgement lost before next write');await new Promise(r=>setTimeout(r,60));}};
  const src=[...document.scripts].map(x=>x.src).find(x=>/\\/assets\\/index-[^/]+\\.js$/.test(x));
  if(!src)throw Error('No observed platform SDK script; use UI fallback');
  const sdk=await import(src),image=await import(new URL('./albumDetail-CmQ0RX5A.js',src).href);
  if(!['L','bc','bb','b9','$'].every(k=>typeof sdk[k]==='function')||typeof image.d!=='function')throw Error('SDK changed; stop before writes');
  const fresh=await(await fetch('/cgi-bin/mmemoticon-bin/home?lang=zh_CN&f=json')).json();
  if(fresh.base_resp?.ret!==0||!Array.isArray(fresh.List))throw Error('Not authenticated');
  if(data.some(a=>fresh.List.some(r=>r.Name===a.name)))throw Error('Album name already exists; reconcile, do not recreate');
  const up=async(file,mediaType)=>{const v=await sdk.L(file,undefined,fd=>{if(mediaType)fd.append('mediatype',mediaType)});if(!v.FileId||v.base_resp?.ret!==0||v.errCode&&v.errCode!==0)throw Error('Upload rejected '+JSON.stringify(v));return {FileId:v.FileId,Md5:v.Md5};};
  const file=v=>new File([Uint8Array.from(atob(v.data),c=>c.charCodeAt(0))],v.name,{type:'image/png'});
  const result=[];
  for(const a of data){
    await checkpoint('upload_started',{name:a.name});
    const assets=[],emojis=[];const tasks=[...a.assets.map((v,i)=>async()=>{assets[i]=await up(file(v));}),...a.emojis.map((v,i)=>async()=>{const f=file(v),original=await up(f);if(original.Md5!==v.md5)throw Error('Original MD5 mismatch');const url=URL.createObjectURL(f);try{const small=await image.d(url,{width:120,height:120}),big=await image.d(url,{width:240,height:240});const s=await up(new File([small.blob],v.name,{type:'image/png'}),'5'),b=await up(new File([big.blob],v.name,{type:'image/png'}));emojis[i]={index:v.index,meaning:v.meaning,md5:b.Md5,smallPicMediaId:s.FileId,bigPicMediaId:b.FileId,originalMd5:original.Md5,originalFileId:original.FileId};}finally{URL.revokeObjectURL(url);}})];let next=0;await Promise.all(Array.from({length:4},async()=>{while(next<tasks.length)await tasks[next++]();}));
    await checkpoint('create_intent',{name:a.name});
    const created=await sdk.bc();if(created.data?.baseResp?.ret!==0||!created.data?.stickerId)throw Error('Create rejected '+JSON.stringify(created));
    const id=created.data.stickerId;await checkpoint('created',{name:a.name,id});
    const context={cropperData:{},originalFileId:{},originalMd5:{},compressCropInfo:{}};
    for(const e of emojis){context.originalMd5[e.md5]=e.originalMd5;context.originalFileId[e.md5]=e.originalFileId;}
    const p={rewardInfo:{agreement:true,word:'谢谢你喜欢我~',begPicMediaId:assets[3].FileId,thanksPicMediaId:assets[4].FileId},authorityInfo:{},activityInfo:{},emojiList:emojis.map(({originalMd5,originalFileId,...e})=>e),downloadArea:['DEF'],validArea:['CN'],isFree:true,designerUin:null,name:a.name,description:a.description,copyright:'捞鱼真不吃鱼',isStatic:true,styleType:1,character:['日常','软萌可爱'],topic:'万能通用',stickerStyle:['人物角色',a.role],coverPicMediaId:assets[0].FileId,mainIconMediaId:assets[1].FileId,panelIconMediaId:assets[2].FileId,clientContext:JSON.stringify(context),stickerId:id};
    const verify=async()=>{const r=await sdk.$({stickerId:id});const d=r.data?.draft;if(r.data?.baseResp?.ret!==0||!d)throw Error('Draft read failed');const c=JSON.parse(d.clientContext);if(d.stickerId!==id||d.name!==a.name||d.emojiList.length!==16||JSON.stringify(d.stickerStyle)!==JSON.stringify(p.stickerStyle)||d.emojiList.some((e,i)=>e.meaning!==emojis[i].meaning||e.md5!==emojis[i].md5||c.originalMd5[e.md5]!==emojis[i].originalMd5)||['coverPicMediaId','mainIconMediaId','panelIconMediaId'].some(k=>d[k]!==p[k])||d.rewardInfo.begPicMediaId!==p.rewardInfo.begPicMediaId||d.rewardInfo.thanksPicMediaId!==p.rewardInfo.thanksPicMediaId)throw Error('Exact-ID draft does not match local package');return d;};
    await checkpoint('save_intent',{name:a.name,id,payload:p});const saved=await sdk.bb(p);if(saved.data?.baseResp?.ret!==0)throw Error('Save rejected '+JSON.stringify(saved));
    await verify();await checkpoint('submit_intent',{name:a.name,id,verifiedImages:16,verifiedAssets:5});
    const submitted=await sdk.b9(p);await checkpoint('submit_response',{name:a.name,id,response:submitted});if(submitted.data?.baseResp?.ret!==0)throw Error('Submit outcome requires reconciliation '+JSON.stringify(submitted));
    await verify();const detail=await(await fetch('/cgi-bin/mmemoticon-bin/stikerpage?stikerid='+id+'&f=json')).json();if(detail.StikerID!==id||![2,3].includes(detail.Status))throw Error('Submission pending reconciliation');
    result.push({name:a.name,id,status:detail.Status,originalImagesMatched:16,meaningsMatched:16,assetsMatched:5,submitCount:1});await checkpoint('verified',{...result.at(-1)});
  }
  const list=await(await fetch('/cgi-bin/mmemoticon-bin/home?lang=zh_CN&f=json')).json();if(list.base_resp?.ret!==0)throw Error('Final list read failed');
  for(const a of result){const rows=list.List.filter(x=>x.Name===a.name);if(rows.length!==1||rows[0].StikerID!==a.id||![2,3].includes(rows[0].Status))throw Error('Final unique-name reconciliation failed');}return result;`;
}
async function publish(bridge, manifest, {log=async()=>{}}={}) {
  const journal=path.join(manifest.logDir,'sdk-journal.json');
  try { await fs.access(journal);throw Error('Journal exists; reconcile existing IDs before restarting publish'); } catch(e){if(e.code!=='ENOENT')throw e;}
  const albums=await Promise.all(manifest.albums.map(inputs));
  const key='__stickerPublish'+crypto.randomBytes(5).toString('hex');let seen=0;
  await json(journal,{state:'intent',at:new Date().toISOString(),albums:albums.map(a=>a.name),key});
  await bridge.attach(manifest.platformTabId);
  await bridge.job(key,browserPublish(albums,key));
  try {
    const state=await bridge.wait(key,{timeout:180000,interval:200,onTick:async s=>{
      if((s?.events?.length||0)>seen){await json(journal,s);for(const e of s.events.slice(seen))await log(e.event,e);seen=s.events.length;await bridge.eval(`window[${JSON.stringify(key)}].ack=${seen}`);}
    }});
    await json(journal,state);return state;
  } catch(e){await log('publish_unknown_or_failed',{message:String(e),journal});throw e;}
}
module.exports={meaning,inputs,browserPublish,publish};
