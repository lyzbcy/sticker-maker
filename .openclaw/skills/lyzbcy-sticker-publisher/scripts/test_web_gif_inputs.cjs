const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {inputs}=require('./web_sdk_publish.cjs');

test('a dynamic album cannot silently upload PNG files as animated stickers',async()=>{
  const parent=path.resolve(os.tmpdir()),dir=await fs.mkdtemp(path.join(parent,'sticker-gif-type-'));
  try{
    const names=['甲','乙','丙','丁','戊','己','庚','辛','壬','癸','子','丑','寅','卯','辰','巳'];
    await fs.writeFile(path.join(dir,'成品清单.json'),JSON.stringify({isStatic:false,files:names.map((meaning,i)=>({meaning,file:i+'.png'}))}));
    await fs.writeFile(path.join(dir,'头像裁切.json'),JSON.stringify({origin:'current_album_sticker'}));
    await assert.rejects(inputs({dir}),/Static\/dynamic file type mismatch/);
  }finally{
    if(!path.resolve(dir).startsWith(parent+path.sep))throw Error('Unexpected cleanup path');
    await fs.rm(dir,{recursive:true});
  }
});
