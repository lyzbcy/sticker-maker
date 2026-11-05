import { describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { createRequire } from 'node:module'

// Exercise the actual python-command IPC registration, including its adapter wiring.
function setup(send) {
  const file = path.resolve('src/main/index.js')
  const source = fs.readFileSync(file, 'utf8')
  const start = source.includes('  const runCommand = createCommandRunner(')
    ? source.indexOf('  const runCommand = createCommandRunner(')
    : source.indexOf("  ipcMain.handle('python-command'")
  const end = source.indexOf("  ipcMain.handle('python-stop'", start)
  const emit = vi.fn(), log = vi.fn(), flattenError = vi.fn(() => ({ status:'error', errors:[{message:'fixture failure'}] }))
  let handler
  const require = createRequire(file)
  const context = { bridge:{send}, operationSequence:0, Date, ipcMain:{handle:(_name, fn) => { handler = fn }}, mainWindow:{isDestroyed:()=>false,webContents:{send:emit}}, diagnosticLog:{log}, PythonBridge:{flattenError} }
  if (source.includes("require('./commandRunner')")) context.createCommandRunner = require('./commandRunner').createCommandRunner
  vm.runInNewContext(source.slice(start, end), context)
  return { invoke:(cmd,args={})=>handler({}, {cmd,args}), emit, log, flattenError,
    tasks:()=>emit.mock.calls.filter(([channel])=>channel==='task-status').map(([,event])=>event) }
}
describe('actual python-command lifecycle', () => {
  it('announces settings persistence before progress and closes it', async () => {
    const h=setup(vi.fn().mockResolvedValue({status:'ok'}))
    await h.invoke('save_prefs')
    expect(h.tasks().map(t=>t.state)).toEqual(['start','end'])
  })
  it('promotes an unlisted command on progress and ends the same task', async () => {
    const h=setup(vi.fn(async (_cmd,_args,progress)=>{progress({message:'881/881',stage:'scan'}); return {status:'ok'}}))
    await h.invoke('unlisted_read_fixture')
    expect(h.tasks().map(t=>t.state)).toEqual(['start','progress','end'])
    expect(new Set(h.tasks().map(t=>t.id)).size).toBe(1)
    expect(h.emit.mock.calls.map(c=>c[0])).toEqual(['task-status','python-progress','task-status','task-status'])
  })
  it('ends promoted work on rejection without turning failure into success', async () => {
    const h=setup(vi.fn(async (_cmd,_args,progress)=>{progress({message:'partial'});throw Error('fixture')}))
    expect((await h.invoke('unlisted_read_fixture')).status).toBe('error')
    expect(h.flattenError).toHaveBeenCalledOnce()
    expect(h.tasks().map(t=>t.state)).toEqual(['start','progress','end'])
  })
  it('does not flash silent polling', async () => {
    const h=setup(vi.fn().mockResolvedValue({status:'ok'}))
    await h.invoke('library_status')
    expect(h.emit).not.toHaveBeenCalled()
  })
  it('ignores callbacks after the owning request settles', async () => {
    let late
    const h=setup(vi.fn(async (_cmd,_args,progress)=>{late=progress;return {status:'ok'}}))
    await h.invoke('unlisted_read_fixture')
    late({message:'late progress'})
    expect(h.emit).not.toHaveBeenCalled()
  })
  it('keeps overlapping requests independent', async () => {
    const finish=[]
    const h=setup(vi.fn((_cmd,_args,progress)=>{progress({message:'scan'});return new Promise(resolve=>finish.push(resolve))}))
    const a=h.invoke('unlisted_a'), b=h.invoke('unlisted_b')
    finish[1]({status:'ok'});await b;finish[0]({status:'ok'});await a
    const tasks=h.tasks(),starts=tasks.filter(t=>t.state==='start'),ends=tasks.filter(t=>t.state==='end')
    expect(starts).toHaveLength(2);expect(starts[0].id).not.toBe(starts[1].id)
    expect(ends.map(t=>t.id)).toEqual([starts[1].id,starts[0].id])
  })
  it('retains original command arguments and result for tracked business work', async () => {
    const result={status:'ok',data:{sentinel:1}}, send=vi.fn().mockResolvedValue(result),h=setup(send)
    const args={path:'fixture-only'}
    expect(await h.invoke('library_refresh',args)).toBe(result)
    expect(send).toHaveBeenCalledWith('library_refresh',args,expect.any(Function))
    expect(h.tasks().map(t=>t.state)).toEqual(['start','end'])
  })
})
