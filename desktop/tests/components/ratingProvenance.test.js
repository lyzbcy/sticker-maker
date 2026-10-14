import { describe, it, expect, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { useEngineStore } from '../../src/renderer/store/engine'
import EpisodeDetailPanel from '../../src/renderer/components/EpisodeDetailPanel.vue'

describe('inherited human ratings', () => {
  it('labels old-art ratings instead of presenting them as newly scored images', async () => {
    setActivePinia(createPinia())
    const store = useEngineStore()
    store.selectedEpisode = { path: '/fixture/episode', meta: { album_name: '作品' }, stickers: [] }
    window.api = { send: vi.fn(async cmd => ({ status:'ok', data:cmd==='get_rating'
      ? { ratings:{开心:{score:4}}, provenance:{inherited_from_other_artwork:true} } : {} })) }
    const wrapper = mount(EpisodeDetailPanel)
    await flushPromises()
    expect(wrapper.text()).toContain('已变化的图片尚未重新评分')
    wrapper.unmount()
  })
})
