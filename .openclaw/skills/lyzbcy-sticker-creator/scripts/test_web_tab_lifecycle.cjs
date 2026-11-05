const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {cleanupCompletedTabs}=require('./web_tab_lifecycle.cjs');
async function fixture(t,tab={}){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-tab-test-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  await fs.mkdir(path.join(dir,'原图'));const raw=Buffer.from('saved source fixture');
  const url='https://chatgpt.com/c/owned-fixture';
  await fs.writeFile(path.join(dir,'原图/grid_4x4.png'),raw);
  await fs.writeFile(path.join(dir,'原图/generation-source.json'),JSON.stringify({sha256:crypto.createHash('sha256').update(raw).digest('hex')}));
  await fs.writeFile(path.join(dir,'ChatGPT响应取证.json'),JSON.stringify({url,text:'complete response'}));
  const calls=[];const bridge={call:async(action)=>{calls.push(action);return action==='list_tabs'?{tabs:[{tabId:7,url,...tab}]}:{closed:true};},attach:async()=>calls.push('attach'),read:async()=>({url})};
  const manifest={albums:[{tabId:7,dir,createdByWorkflow:true,processMs:2,conversationUrl:url}]};
  return {dir,bridge,calls,manifest};
}
test('closes saved workflow tab once and persists closure',async t=>{
  const f=await fixture(t);let saves=0;
  assert.equal((await cleanupCompletedTabs(f.bridge,f.manifest,{save:async()=>saves++})).closed,1);
  assert.equal(saves,2);assert.ok(f.manifest.albums[0].tabClosedAt);
  assert.equal((await cleanupCompletedTabs(f.bridge,f.manifest)).closed,0);
  assert.equal(f.calls.filter(a=>a==='close_tab').length,1);
});
test('changed source prevents closing',async t=>{
  const f=await fixture(t);await fs.appendFile(path.join(f.dir,'原图/grid_4x4.png'),'changed');
  await assert.rejects(cleanupCompletedTabs(f.bridge,f.manifest),/intact local source/);
  assert.ok(!f.calls.includes('close_tab'));
});
test('borrowed or navigated tabs and unresolved jobs are retained',async t=>{
  for(const tab of [{borrowed:true},{url:'https://example.com/'}]){
    const f=await fixture(t,tab);assert.equal((await cleanupCompletedTabs(f.bridge,f.manifest)).closed,0);
    assert.ok(!f.calls.includes('attach'));
  }
  const f=await fixture(t);delete f.manifest.albums[0].processMs;
  assert.equal((await cleanupCompletedTabs(f.bridge,f.manifest)).closed,0);
});
