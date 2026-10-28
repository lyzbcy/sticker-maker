import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ResourceLibraryPanel from '../../src/renderer/components/ResourceLibraryPanel.vue'
const wrappers=[]
let send, off
const preview={plan_id:'retained-plan',mode:'backup',cleanup:false,entries:[],missing:[],bytes:0}
function open(){const w=mount(ResourceLibraryPanel);wrappers.push(w);return w}
beforeEach(()=>{
 setActivePinia(createPinia());off=vi.fn()
 send=vi.fn(async cmd=>({status:'ok',data:cmd==='library_preview'?preview:{}}))
 window.api={send,selectDirectory:vi.fn(async()=>'/fixture/target'),onProgress:vi.fn(()=>vi.fn()),onRestarting:vi.fn(),stop:vi.fn(),toFileUrl:p=>p}
})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.useRealTimers();vi.restoreAllMocks()})
describe('resource library refactor lifecycle and UX boundaries',()=>{
 it('releases the exact progress subscription when its panel unmounts',async()=>{
  const w=open();await flushPromises();const panelOff=window.api.onProgress.mock.results.at(-1).value;expect(panelOff).not.toHaveBeenCalled()
  w.unmount();wrappers.splice(wrappers.indexOf(w),1);expect(panelOff).toHaveBeenCalledTimes(1)
 })
 it('keeps two panel models independent rather than sharing form state',async()=>{
  const a=open(),b=open();await flushPromises()
  await a.get('[data-test=account-id]').setValue('account-A')
  expect(b.get('[data-test=account-id]').element.value).toBe('')
  expect(a.get('[data-test=account-id]').element.value).toBe('account-A')
 })
 it('does not discard a selected destination or valid preview when the chooser is cancelled',async()=>{
  const w=open();await flushPromises()
  await w.get('[data-test=export-target]').trigger('click');await flushPromises()
  await w.get('[data-test=preview-export]').trigger('click');await flushPromises()
  expect(w.find('[data-test=preview-summary]').exists()).toBe(true)
  window.api.selectDirectory.mockResolvedValueOnce({canceled:true})
  await w.get('[data-test=export-target]').trigger('click');await flushPromises()
  expect(w.get('[data-test=export-target-path]').element.value).toBe('/fixture/target')
  expect(w.find('[data-test=preview-summary]').exists()).toBe(true)
  expect(w.get('[data-test=execute-export]').isDisabled()).toBe(false)
 })
 it('reports chooser failure without losing the prior source selection',async()=>{
  const w=open();await flushPromises()
  await w.get('[data-test=choose-library]').trigger('click');await flushPromises()
  window.api.selectDirectory.mockRejectedValueOnce(new Error('fixture chooser failed'))
  await w.get('[data-test=choose-library]').trigger('click');await flushPromises()
  expect(w.get('[data-test=source-path]').element.value).toBe('/fixture/target')
  expect(w.get('[data-test=library-error]').text()).toContain('fixture chooser failed')
 })
 it('sends shared deletion once while the result is pending and preserves confirmation',async()=>{
  let finish;send.mockImplementation(async cmd=>cmd==='library_delete'?await new Promise(r=>finish=r):{status:'ok',data:{}})
  const confirm=vi.spyOn(window,'confirm').mockReturnValue(true)
  const w=open();await flushPromises();await w.get('[data-test=work-id]').setValue('fixture-work')
  await w.get('[data-test=delete-work]').trigger('click');await w.get('[data-test=delete-work]').trigger('click')
  expect(send.mock.calls.filter(([cmd])=>cmd==='library_delete')).toHaveLength(1)
  expect(confirm).toHaveBeenCalledTimes(1)
  finish({status:'ok',data:{}});await flushPromises();expect(w.get('[data-test=delete-work]').isDisabled()).toBe(false)
 })
 it('never sends shared deletion after confirmation is declined',async()=>{
  vi.spyOn(window,'confirm').mockReturnValue(false)
  const w=open();await flushPromises();await w.get('[data-test=work-id]').setValue('fixture-work')
  await w.get('[data-test=delete-work]').trigger('click')
  expect(send.mock.calls.some(([cmd])=>cmd==='library_delete')).toBe(false)
 })
 it('clears the conflict refresh retry timer and poller on unmount',async()=>{
  vi.useFakeTimers();send.mockImplementation(async cmd=>({status:'ok',data:cmd==='library_status'?{conflicts:[{work_id:'work',heads:[{revision_id:'rev'}]}]}:{}}))
  const w=open();await flushPromises();await w.get('[data-test=choose-rev]').trigger('click');await flushPromises()
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  w.unmount();wrappers.splice(wrappers.indexOf(w),1);expect(vi.getTimerCount()).toBe(0)
 })
 it('ignores late conflict completion after unmount without creating a new timer or status read',async()=>{
  vi.useFakeTimers();let finish
  send.mockImplementation(async cmd=>cmd==='library_resolve'?await new Promise(r=>finish=r):{status:'ok',data:cmd==='library_status'?{conflicts:[{work_id:'work',heads:[{revision_id:'late-rev'}]}]}:{}})
  const w=open();await flushPromises();await w.get('[data-test=choose-late-rev]').trigger('click')
  const before=send.mock.calls.filter(([cmd])=>cmd==='library_status').length
  w.unmount();wrappers.splice(wrappers.indexOf(w),1);finish({status:'ok',data:{}});await flushPromises()
  expect(vi.getTimerCount()).toBe(0)
  expect(send.mock.calls.filter(([cmd])=>cmd==='library_status')).toHaveLength(before)
 })

})
