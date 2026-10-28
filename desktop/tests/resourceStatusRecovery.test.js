import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { createLibraryState } from '../src/renderer/components/resource-library/state'
import { createLibraryActions } from '../src/renderer/components/resource-library/actions'
let scope
afterEach(()=>scope?.stop())
function setup() {
  scope=effectScope()
  return scope.run(()=>{
    const state=createLibraryState();state.mounted.value=true
    const send=vi.fn(),gateway={send,api:()=>({}),responseError:(res,fallback)=>res?.errors?.[0]?.message||fallback,exceptionError:(err)=>err.message}
    const actions=createLibraryActions(state,gateway,vi.fn())
    return {state,send,actions}
  })
}
describe('resource status error ownership',()=>{
  it('clears its temporary busy read error after quiet recovery',async()=>{
    const {state,send,actions}=setup()
    send.mockResolvedValueOnce({status:'error',errors:[{message:'save_prefs busy'}]}).mockResolvedValueOnce({status:'ok',data:{connected:true}})
    await actions.refreshStatus();expect(state.errorMessage.value).toBe('save_prefs busy')
    await actions.refreshStatus({quiet:true})
    expect(state.errorMessage.value).toBe('');expect(state.library.value.connected).toBe(true)
  })
  it('clears a transport read error after successful quiet recovery',async()=>{
    const {state,send,actions}=setup()
    send.mockRejectedValueOnce(Error('temporary read failure')).mockResolvedValueOnce({status:'ok',data:{connected:true}})
    await actions.refreshStatus();await actions.refreshStatus({quiet:true})
    expect(state.errorMessage.value).toBe('')
  })
  it('does not erase an unrelated operation error',async()=>{
    const {state,send,actions}=setup()
    send.mockResolvedValueOnce({status:'error'}).mockResolvedValueOnce({status:'ok',data:{connected:true}})
    await actions.refreshStatus();state.errorMessage.value='导出失败：请重试'
    await actions.refreshStatus({quiet:true})
    expect(state.errorMessage.value).toBe('导出失败：请重试')
  })
  it('does not overwrite an operation error on silent poll failure',async()=>{
    const {state,send,actions}=setup();state.errorMessage.value='导出失败'
    send.mockResolvedValue({status:'error',errors:[{message:'busy'}]})
    await actions.refreshStatus({quiet:true});expect(state.errorMessage.value).toBe('导出失败')
  })
})
