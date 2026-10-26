import { describe,it,expect,vi,beforeEach } from 'vitest'
import { singleMetrics,observationGroups,rankSingles } from '../src/renderer/utils/singleMetrics'
import { mount,flushPromises } from '@vue/test-utils'
import { createPinia,setActivePinia } from 'pinia'
import { useEngineStore } from '../src/renderer/store/engine'
import SingleStickerMetrics from '../src/renderer/components/SingleStickerMetrics.vue'
const snapshot=(id='a',date='10月24日',sends=0)=>({item_id:id,album_name:id,period_kind:'platform_daily',captured_at:'2026-10-26T01:00:00+00:00',capture_date:'2026-10-26',items:[{md5:id.repeat(32),index:'01',meaning:'开心'+id,sends,data_time:date,matched:true}]})
describe('daily single-sticker report',()=>{
 beforeEach(()=>{window.api={send:vi.fn(),onProgress:vi.fn(),onRestarting:vi.fn(),onExit:vi.fn()}})
 it('keeps true zero, deduplicates identity, excludes invalid values, never mixes dates',()=>{
  const a=snapshot(),b=snapshot('b','10月24日',27),c=snapshot('c','10月23日',100)
  const rows=singleMetrics([a,a,b,c]);expect(rows).toHaveLength(3);expect(observationGroups(rows)).toHaveLength(2)
  const ranked=rankSingles(rows,'2026-10-26 | 10月24日');expect(ranked.map(r=>r.sends)).toEqual([27,0])
  b.items[0].sends=null;expect(singleMetrics([b])).toHaveLength(0)
 })
 it('uses newest cache per album and separates capture days',()=>{
  const old=snapshot(),fresh={...snapshot(),captured_at:'2026-10-27T01:00:00+00:00',capture_date:'2026-10-27'}
  expect(singleMetrics([fresh,old])[0].capture_date).toBe('2026-10-27')
 })

})
