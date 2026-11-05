// Close only workflow-created tabs whose original image and response are saved.
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
async function cleanupCompletedTabs(bridge,manifest,{save=async()=>{},log=async()=>{}}={}) {
  const tabs=(await bridge.call('list_tabs')).tabs;
  let closed=0;
  for(const a of manifest.albums||[]) {
    if(!a.createdByWorkflow||a.tabClosedAt||!(a.processMs||a.downloadedAt)||!a.conversationUrl)continue;
    const root=a.dir;
    const proof=JSON.parse(await fs.readFile(path.join(root,a.sourceProofFile||'原图/generation-source.json'),'utf8'));
    const response=JSON.parse(await fs.readFile(path.join(root,a.responseFile||'ChatGPT响应取证.json'),'utf8'));
    const raw=await fs.readFile(path.join(root,a.sourceFile||'原图/grid_4x4.png'));
    if(crypto.createHash('sha256').update(raw).digest('hex')!==proof.sha256||response.url!==a.conversationUrl||!response.text)throw Error('Tab cleanup requires intact local source and response');
    const tab=tabs.find(t=>t.tabId===a.tabId);
    if(!tab){a.tabClosedAt=Date.now();a.tabCleanupResult='already_absent';await save();continue;}
    if(tab.borrowed||tab.url!==a.conversationUrl||!/^https:\/\/chatgpt\.com\/c\//.test(tab.url)){
      await log('tab_cleanup_skipped',{tabId:a.tabId,reason:'Tab identity changed or borrowed'});continue;
    }
    a.tabCloseIntentAt=Date.now();await save();
    await bridge.attach(a.tabId);
    const current=await bridge.read('({url:location.href})');
    if(current.url!==a.conversationUrl)throw Error('Tab navigated before cleanup; retained');
    const result=await bridge.call('close_tab');
    if(!result.closed)throw Error('Tab close not confirmed');
    a.tabClosedAt=Date.now();a.tabCleanupResult='closed';await save();closed++;
    await log('generation_tab_closed',{tabId:a.tabId,url:a.conversationUrl});
  }
  return {closed};
}
module.exports={cleanupCompletedTabs};
