import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import Wizard from '../../src/renderer/components/Wizard.vue'
import WorkspaceTabs from '../../src/renderer/components/WorkspaceTabs.vue'
import HealthPanel from '../../src/renderer/components/HealthPanel.vue'
import StatusBar from '../../src/renderer/components/StatusBar.vue'
import SettingsPanel from '../../src/renderer/components/SettingsPanel.vue'
import { useEngineStore } from '../../src/renderer/store/engine'
beforeEach(()=>{
 setActivePinia(createPinia())
 window.api={send:vi.fn(async()=>({status:'ok',data:{}})),onProgress:vi.fn(),onRestarting:vi.fn(),
 diagnosticSnapshot:vi.fn(async()=>({debug:false})),diagnosticMode:vi.fn(async debug=>({debug})),exportDiagnostics:vi.fn(async()=>({ok:true}))}
})
describe('Word task usability requirements',()=>{
 for(let step=0;step<5;step++) it(`exits tutorial at step ${step+1} even if Codex is unavailable`,async()=>{
  const store=useEngineStore();store.phase='wizard';const w=mount(Wizard);await flushPromises()
  for(let i=0;i<step;i++){await w.get('.btn-primary').trigger('click');await flushPromises()}
  await w.get('[data-test=exit-tutorial]').trigger('click')
  expect(store.phase).toBe('main');expect(window.api.send).not.toHaveBeenCalledWith('save_prefs',expect.anything());w.unmount()
 })
 it('keeps all stickers and warnings one click away in the workspace tabs',async()=>{
  const store=useEngineStore();const w=mount(WorkspaceTabs)
  await w.get('[data-test=tab-allStickers]').trigger('click');expect(store.phase).toBe('allStickers')
  await w.get('[data-test=tab-health]').trigger('click');expect(store.phase).toBe('health');w.unmount()
 })
 it('explains missing-component impact and provides quick repair and debug actions',async()=>{
  const w=mount(HealthPanel);await flushPromises()
  expect(w.text()).toContain('浏览、评分和导出不受影响');expect(w.text()).toContain('快速处理生图环境')
  await w.get('[data-test=debug-mode]').setValue(true);await flushPromises()
  expect(window.api.diagnosticMode).toHaveBeenCalledWith(true);w.unmount()
 })
 it('shows long-running synchronization context even when generation is idle',async()=>{
  const store=useEngineStore();store.activeTasks={sync:{startedAt:Date.now()-12000,stage:'sync',message:'正在读取平台作品',percent:50}}
  const w=mount(StatusBar);expect(w.text()).toContain('正在读取平台作品');expect(w.text()).toContain('已用时');expect(w.text()).toContain('50%');w.unmount()
 })
 it('opens the quick account repair destination with the actual saved credential status',async()=>{
  const store=useEngineStore();store.settingsTab='publish'
  window.api.send.mockImplementation(async cmd=>({status:'ok',data:cmd==='publish_credentials_status'?{configured:true,account:'fixture@example.test',backend:'keyring'}:{}}))
  const w=mount(SettingsPanel);await flushPromises()
  expect(w.text()).toContain('已保存 fixture@example.test');expect(w.get('input.pub-input').attributes('placeholder')).toBe('fixture@example.test');w.unmount()
 })
})
