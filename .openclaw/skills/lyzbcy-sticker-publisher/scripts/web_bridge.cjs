// Shared transport for the existing creator/publisher skills. No cookies leave the page.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {execFile} = require('node:child_process');
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function json(file, data) {
  await fs.mkdir(path.dirname(file), {recursive:true});
  const tmp = file + '.writing';
  await fs.writeFile(tmp, JSON.stringify(data, null, 2));
  await fs.rename(tmp, file);
}
class Bridge {
  constructor({url='http://127.0.0.1:10086', session='sticker-web-trial-20261105', log=async()=>{}}={}) {
    this.url=url; this.session=session; this.log=log;
  }
  async call(action, args={}) {
    const file=path.join(os.tmpdir(), 'sticker-wb-'+crypto.randomUUID()+'.json');
    await fs.writeFile(file, JSON.stringify({action,args,session:this.session}));
    const started=Date.now();
    try {
      const raw=await new Promise((resolve,reject)=>execFile('curl.exe', ['-sS','--max-time','20','-X','POST',this.url+'/command','-H','Content-Type: application/json','--data-binary','@'+file], {encoding:'utf8',maxBuffer:40e6,windowsHide:true}, (e,out,err)=>e?reject(Error(err)):resolve(out)));
      const result=JSON.parse(raw);
      if(!result.ok) throw Error(JSON.stringify(result.error));
      await this.log('bridge', {action,ms:Date.now()-started});
      return result.data;
    } finally { await fs.unlink(file).catch(()=>{}); }
  }
  async eval(code) { return (await this.call('evaluate',{code})).value; }
  async read(code) { const v=await this.eval('JSON.stringify('+code+')');return JSON.parse(v); }
  async attach(tabId) { return this.call('attach_tab',{tabId}); }
  // Never await a browser Promise through the bridge: older daemons can hang.
  async job(key, body) {
    await this.eval(`(()=>{window[${JSON.stringify(key)}]={state:'running',startedAt:Date.now()};(async()=>{${body}})().then(result=>Object.assign(window[${JSON.stringify(key)}],{state:'done',endedAt:Date.now(),result})).catch(e=>Object.assign(window[${JSON.stringify(key)}],{state:'error',endedAt:Date.now(),error:String(e)}));return 'started'})()`);
  }
  async wait(key, {timeout=240000,interval=500,onTick=async()=>{}}={}) {
    const started=Date.now();
    while(Date.now()-started<timeout) {
      const state=await this.read('window['+JSON.stringify(key)+']');
      await onTick(state);
      if(state?.state==='error') throw Error(state.error);
      if(state?.state==='done') return state;
      await sleep(interval);
    }
    throw Error('Browser job result unknown; reconcile journal before any new write: '+key);
  }
}
module.exports={Bridge,json,sleep};
