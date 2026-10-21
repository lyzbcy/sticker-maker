import { afterEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { DiagnosticLog } from '../src/main/diagnosticLog'
const logs=[]
afterEach(async () => { for(const log of logs.splice(0)) await log.close(); vi.restoreAllMocks();vi.useRealTimers() })
async function fixture(options={}) { const root=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-logs-')); const log=new DiagnosticLog(root,options); logs.push(log); return log }
describe('buffered local diagnostics', () => {
  it('flushes the timer batch after five seconds and leaves idle intervals unwritten',async()=>{
    vi.useFakeTimers({toFake:['setInterval','clearInterval']})
    const log=await fixture();const append=vi.spyOn(fs,'appendFile');log.log({message:'buffered'})
    await vi.advanceTimersByTimeAsync(4999);expect(append).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1);await log.work;expect(append).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10000);expect(append).toHaveBeenCalledTimes(1)
  })
  it('batches ordinary records and does not write one file per event',async()=>{
    const log=await fixture(); const append=vi.spyOn(fs,'appendFile')
    for(let i=0;i<40;i++) log.log({message:'step '+i})
    expect(append).not.toHaveBeenCalled()
    await log.flush(); expect(append).toHaveBeenCalledTimes(1)
    expect((await log.snapshot()).text).toContain('step 39')
  })
  it('preserves records across a new session and normal exit',async()=>{
    const log=await fixture(); log.log({message:'previous session'}); await log.close()
    const second=new DiagnosticLog(log.root); logs.push(second); await second.init()
    expect((await second.snapshot()).text).toContain('previous session')
  })
  it('redacts before disk and only records detail in debug mode',async()=>{
    const log=await fixture()
    log.log({message:'password=hidden',details:{password:'private-secret',step:'detail-sample'}})
    await log.flush(); let text=(await log.snapshot(99999,true)).text
    expect(text).not.toContain('hidden');expect(text).not.toContain('detail-sample')
    await log.setDebug(true)
    log.log({message:'diagnostic',details:{password:'private-secret',token:'private-token',step:'detail-sample'}})
    text=(await log.snapshot(99999,true)).text
    expect(text).toContain('detail-sample');expect(text).not.toContain('private-secret');expect(text).not.toContain('private-token')
  })
  it('immediately flushes errors without waiting for the batch interval',async()=>{
    const log=await fixture();log.log({level:'error',message:'fault-context'});await log.work
    expect((await fs.readdir(log.root)).some(n=>n.endsWith('.jsonl'))).toBe(true)
    expect(log.queue.length).toBe(0)
  })
  it('rotates and enforces total byte and age limits',async()=>{
    const log=await fixture({fileBytes:250,totalBytes:600})
    for(let i=0;i<5;i++){log.log({message:'x'.repeat(100)});await log.flush()}
    expect((await log.files()).reduce((n,f)=>n+f.size,0)).toBeLessThanOrEqual(600)
    log.now=()=>Date.now()+8*86400000;await log.prune();expect(await log.files()).toHaveLength(0)
  })
  it('survives an unwritable location and exposes memory context',async()=>{
    const folder=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-disk-fail-'));const root=path.join(folder,'file');await fs.writeFile(root,'fixture')
    const log=new DiagnosticLog(root);logs.push(log);log.log({level:'error',message:'saved in memory'});await log.work
    const data=await log.snapshot();expect(data.error).toContain('写入失败');expect(data.text).toContain('saved in memory')
  })
})
