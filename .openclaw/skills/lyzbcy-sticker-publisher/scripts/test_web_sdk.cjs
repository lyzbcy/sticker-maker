const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {meaning,publish,inputs}=require('./web_sdk_publish.cjs');
test('known platform rejection is normalized before any upload',()=>{
  assert.equal(meaning('啊？'),'啊');assert.equal(meaning('辛苦啦！'),'辛苦啦');
  for(const bad of ['？？','123','五个字不行','OK'])assert.throws(()=>meaning(bad));
});
test('existing journal prevents recreation or replay, even with an empty manifest',async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-journal-'));
  try{
    await fs.writeFile(path.join(dir,'sdk-journal.json'),'{}');let calls=0;
    await assert.rejects(publish({attach(){calls++;}},{logDir:dir,albums:[]}),/Journal exists/);
    assert.equal(calls,0);
  }finally{await fs.rm(dir,{recursive:true});}
});
test('base portrait provenance is rejected before uploads',async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-source-'));
  try{
    await fs.writeFile(path.join(dir,'成品清单.json'),JSON.stringify({files:[]}));
    await fs.writeFile(path.join(dir,'头像裁切.json'),JSON.stringify({origin:'reference_base'}));
    await assert.rejects(inputs({dir}),/this album sticker/);
  }finally{await fs.rm(dir,{recursive:true});}
});
