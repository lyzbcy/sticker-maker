import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import EpisodesPanel from '../../src/renderer/components/EpisodesPanel.vue'
let episodes
beforeEach(()=>{
  setActivePinia(createPinia())
  episodes=[{name:'failure',path:'E:/fixture',album_name:'失败原作品',platform_status:'预约上架失败',published:true,complete:true,can_shelf:true}]
  window.api={send:vi.fn(async cmd=>({status:'ok',data:cmd==='list_episodes'?{episodes}:cmd==='list_series'?{series:[]}:cmd==='shelf_passed'?{published:1,failed:[],source:'api'}:{}})),
    toFileUrl:p=>`file://${p}`,onProgress:vi.fn(),onExit:vi.fn(),onRestarting:vi.fn(),onUpdateProgress:vi.fn()}
})
it('预约失败计入名单，保持失败红标，点击只调用上架而不重新投稿',async()=>{
  const w=mount(EpisodesPanel);await flushPromises()
  expect(w.get('.status-badge').classes()).toContain('st-reject')
  expect(w.get('.shelf-btn').text()).toContain('1 弹')
  expect(w.get('.shelf-btn').attributes('title')).toContain('预约失败')
  await w.get('.shelf-btn').trigger('click');await flushPromises()
  expect(window.api.send).toHaveBeenCalledWith('shelf_passed',{})
  expect(window.api.send).not.toHaveBeenCalledWith('publish_episode',expect.anything())
  w.unmount()
})
it('冲突/离线资源明确不可上架时仍排除',async()=>{
  episodes[0].can_shelf=false
  const w=mount(EpisodesPanel);await flushPromises()
  expect(w.find('.shelf-btn').exists()).toBe(false);w.unmount()
})
