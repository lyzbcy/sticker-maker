import { describe, it, expect, vi } from 'vitest'
import { metric, albumMetrics, total, rank } from '../src/renderer/utils/analytics'
import { remakePrompt } from '../src/renderer/utils/featuredRemake'
import { createPinia, setActivePinia } from 'pinia'
import { useEngineStore } from '../src/renderer/store/engine'
import { mount, flushPromises } from '@vue/test-utils'
import AnalyticsPanel from '../src/renderer/components/AnalyticsPanel.vue'
describe('analytics and income freshness',()=>{
 it('preserves zero and missing values, deduplicates platform identity',()=>{
  expect(metric('0')).toBe(0);expect(metric('-')).toBe(null);expect(metric('')).toBe(null);expect(metric('1,234')).toBe(1234)
  const rows=albumMetrics([{name:'a',platform_item_id:'p',platform_sends:'0'},{name:'b',platform_item_id:'p',platform_sends:55},{name:'c',platform_sends:'-'}])
  expect(rows).toHaveLength(2);expect(total(rows,'sends')).toEqual({value:0,known:1});expect(rank(rows,'sends')[0].name).toBe('a')
  expect(total([],'sends').value).toBe(null)
 })
 it('successful income replaces old data; failure preserves it and states stale',()=>{
  setActivePinia(createPinia());const store=useEngineStore()
  store.acceptIncome({summary:{total_heat:'10'}});store.acceptIncome({summary:{total_heat:'20'}})
  expect(store.income.summary.total_heat).toBe('20');store.acceptIncome({error:'timeout'})
  expect(store.income.summary.total_heat).toBe('20');expect(store.incomeError).toBe('timeout')
 })
 it('renders dashboard and refreshes real command response',async()=>{
  const pinia=createPinia();setActivePinia(pinia);const store=useEngineStore()
  store.episodes=[{name:'a',platform_item_id:'a'}]
  vi.spyOn(store,'loadEpisodes').mockResolvedValue();vi.spyOn(store,'loadIncome').mockResolvedValue()
  window.api={send:vi.fn().mockResolvedValue({status:'ok',data:{list_complete:true,income:{summary:{total_heat:'100',total_tips:'0',withdrawable:'2.5'}}}})}
  const w=mount(AnalyticsPanel,{global:{plugins:[pinia]}});await flushPromises();await w.get('button').trigger('click');await flushPromises()
  expect(window.api.send).toHaveBeenCalledWith('sync_platform_status',{fetch_reasons:false});expect(w.text()).toContain('100');expect(w.text()).toContain('不将整套发送量分摊到单图')
 })
 it('produces customized free remake instructions without altering originals',()=>{
  const g={album_name:'第1弹'},st={path:'C:/reference.png',meaning:'开心'}
  const prompt=remakePrompt(g,st,'轮廓脏边');expect(prompt).toContain('轮廓脏边');expect(prompt).toContain('免费发布');expect(prompt).toContain('实质性重绘');expect(st.path).toBe('C:/reference.png')
 })
})
