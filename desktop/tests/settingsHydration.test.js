import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from '../src/renderer/components/SettingsPanel.vue'
let store, wrapper
vi.mock('../src/renderer/store/engine',()=>({useEngineStore:()=>store}))
function setup(prefs) {
  store=reactive({prefs:structuredClone(prefs),settingsTab:'publish',loadCharacters:vi.fn(),savePrefs:vi.fn().mockResolvedValue(true)})
  window.api={send:vi.fn().mockResolvedValue({status:'ok',data:{configured:false}})}
  wrapper=mount(SettingsPanel,{global:{stubs:{WizardStepBase:true,WizardStepMode:true,WizardStepChar:true,WizardStepPref:true,ResourceLibraryPanel:true}}})
}
afterEach(()=>{wrapper?.unmount();wrapper=null;vi.useRealTimers()})
describe('settings hydration is read-only',()=>{
  it.each([
    {browser_headless:false,sticker_price:0,price_probs:{}},
    {browser_headless:true,sticker_price:10,price_probs:{}},
    {browser_headless:true,sticker_price:0,price_probs:{'0':0.85,'10':0.15}},
  ])('does not save or normalize persisted settings on mount: %j',async prefs=>{
    setup(prefs);await flushPromises()
    expect(store.savePrefs).not.toHaveBeenCalled()
    expect(store.prefs).toEqual(prefs)
    expect(wrapper.text()).not.toContain('✓ 已保存')
  })
  it('persists one explicit price change',async()=>{
    setup({browser_headless:false,sticker_price:0,price_probs:{}});await flushPromises()
    await wrapper.get('input[value="paid10"]').setValue(true);await flushPromises()
    expect(store.savePrefs).toHaveBeenCalledOnce();expect(store.prefs.sticker_price).toBe(10)
    expect(wrapper.text()).toContain('✓ 已保存')
  })
  it('keeps linked probability sliders to one save per user change',async()=>{
    setup({browser_headless:false,sticker_price:0,price_probs:{'0':0.85,'10':0.15}});await flushPromises()
    store.savePrefs.mockClear()
    await wrapper.get('[data-test="price-prob-paid"]').setValue(30);await flushPromises()
    expect(store.savePrefs).toHaveBeenCalledOnce();expect(store.prefs.price_probs).toEqual({'0':0.7,'10':0.3})
  })
  it('does not claim success when the store rejects validation',async()=>{
    setup({browser_headless:false,sticker_price:0,price_probs:{}});await flushPromises()
    store.savePrefs.mockResolvedValue(false)
    await wrapper.get('input[value="paid10"]').setValue(true);await flushPromises()
    expect(wrapper.text()).not.toContain('✓ 已保存');expect(wrapper.text()).toContain('设置未保存')
  })
  it('retains changed values and presents a retryable save error',async()=>{
    setup({browser_headless:false,sticker_price:0,price_probs:{}});await flushPromises()
    store.savePrefs.mockRejectedValue(Error('fixture'))
    await wrapper.get('input[value="paid10"]').setValue(true);await flushPromises()
    expect(store.prefs.sticker_price).toBe(10);expect(wrapper.text()).toContain('设置保存失败')
  })
  it('does not schedule a saved indicator after unmount',async()=>{
    vi.useFakeTimers();setup({browser_headless:false,sticker_price:0,price_probs:{}});await flushPromises()
    let finish;store.savePrefs.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
    await wrapper.get('input[value="paid10"]').setValue(true)
    wrapper.unmount();wrapper=null;finish(true);await flushPromises()
    expect(vi.getTimerCount()).toBe(0)
  })
})
