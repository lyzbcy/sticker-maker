import { describe,it,expect,vi,beforeEach } from 'vitest'
import { mount,flushPromises } from '@vue/test-utils'
import { createPinia,setActivePinia } from 'pinia'
import { useEngineStore } from '../src/renderer/store/engine'
import SingleStickerMetrics from '../src/renderer/components/SingleStickerMetrics.vue'
const response=(offset=0)=>({rows:Array.from({length:20},(_,i)=>({item_id:'a',md5:String(i+offset),meaning:'图'+(i+offset),album_name:'作品',sends:7753-i-offset,data_time:'10月24日',image_path:'C:/图 #'+i+'.png',share:.1})),total:7753,groups:[{key:'day',label:'10月24日'}],summary:{sends:100,zero:5,nonzero:7748}})
function setup(send){const pinia=createPinia();setActivePinia(pinia);useEngineStore().episodes=[{platform_item_id:'a',platform_status:'已上架'}];window.api={send,onProgress:()=>()=>{},toFileUrl:p=>'file:///'+encodeURI(p)};return mount(SingleStickerMetrics,{global:{plugins:[pinia]}})}
describe('bounded analytics IPC and original images',()=>{
 beforeEach(()=>{vi.useRealTimers();window.api={onProgress:vi.fn(),onRestarting:vi.fn(),onExit:vi.fn()}})
 it('loads only 20 over IPC, next page requests 20 and shows original image modal',async()=>{
  const send=vi.fn(async(cmd,args)=>({status:'ok',data:response(args.offset)})),w=setup(send);await flushPromises()
  expect(send).toHaveBeenCalledTimes(1);expect(send).toHaveBeenCalledWith('get_sticker_metrics',expect.objectContaining({paginated:true,offset:0,limit:20}))
  expect(w.findAll('tbody tr')).toHaveLength(20);expect(w.findAll('tbody img')).toHaveLength(20);expect(w.text()).toContain('第 1/388 页');expect(w.find('img').attributes('loading')).toBe('lazy')
  await w.get('[aria-label="查看原图 图0"]').trigger('click');expect(w.find('[role="dialog"]').exists()).toBe(true);await w.get('[role="dialog"] button').trigger('click');expect(w.find('[role="dialog"]').exists()).toBe(false)
  await w.get('[data-test="next-single"]').trigger('click');await flushPromises();expect(send).toHaveBeenLastCalledWith('get_sticker_metrics',expect.objectContaining({offset:20,limit:20}));expect(w.text()).toContain('图20');w.unmount()
 })
 it('debounces search and requests ascending including zero without loading all rows',async()=>{
  const send=vi.fn(async()=>({status:'ok',data:response()})),w=setup(send);await flushPromises();vi.useFakeTimers()
  await w.get('[aria-label="搜索表情"]').setValue('笑');await w.get('[aria-label="搜索表情"]').setValue('笑死');await vi.advanceTimersByTimeAsync(260);await flushPromises();expect(send).toHaveBeenLastCalledWith('get_sticker_metrics',expect.objectContaining({query:'笑死',offset:0}));expect(send).toHaveBeenCalledTimes(2)
  await w.get('[aria-label="单图排序"]').setValue('asc');await flushPromises();expect(send).toHaveBeenLastCalledWith('get_sticker_metrics',expect.objectContaining({sort:'asc'}));w.unmount()
 })
 it('keeps current page on failure, explicitly labels missing and broken images',async()=>{
  const data=response();data.rows[0].image_path='';const send=vi.fn().mockResolvedValueOnce({status:'ok',data}).mockRejectedValueOnce(Error('网络错误'))
  const w=setup(send);await flushPromises();expect(w.text()).toContain('本地原图未精确匹配');await w.get('tbody img').trigger('error');expect(w.text()).toContain('原图加载失败');await w.get('[data-test="next-single"]').trigger('click');await flushPromises();expect(w.text()).toContain('网络错误');expect(w.findAll('tbody tr')).toHaveLength(20);w.unmount()
 })
 it('ignores late response after scope change',async()=>{
  let old;const send=vi.fn().mockImplementationOnce(()=>new Promise(r=>old=r)).mockResolvedValue({status:'ok',data:response(20)});const w=setup(send);await flushPromises();useEngineStore().episodes=[{platform_item_id:'b'}];await flushPromises();old({status:'ok',data:response()});await flushPromises();expect(w.get('tbody').text()).toContain('图20');expect(w.get('tbody').text()).not.toContain('图0');w.unmount()
 })
 it('cancels exact request and uses compact sync result',async()=>{
  let progress,resolve;const pinia=createPinia();setActivePinia(pinia);useEngineStore().episodes=[{platform_item_id:'a',platform_status:'已上架'}]
  const send=vi.fn(cmd=>cmd==='get_sticker_metrics'?Promise.resolve({status:'ok',data:response()}):new Promise(r=>resolve=r)),stop=vi.fn().mockResolvedValue({status:'ok'});window.api={send,stop,onProgress:cb=>{progress=cb;return ()=>{}}}
  const w=mount(SingleStickerMetrics,{global:{plugins:[pinia]}});await flushPromises();await w.get('[data-test="fetch-singles"]').trigger('click');progress({stage:'single_metrics',id:'req',message:'1/486'});await flushPromises();await w.get('[data-test="cancel-singles"]').trigger('click');expect(stop).toHaveBeenCalledWith('req');expect(send).toHaveBeenCalledWith('sync_sticker_metrics',{paginated:true});resolve({status:'ok',data:{cancelled:true,updated:1,total:486}});await flushPromises();expect(w.text()).toContain('已取消');w.unmount()
 })
})
