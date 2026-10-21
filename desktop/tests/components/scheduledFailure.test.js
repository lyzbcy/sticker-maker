import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import EpisodesPanel from '../../src/renderer/components/EpisodesPanel.vue'
import EpisodeDetailPanel from '../../src/renderer/components/EpisodeDetailPanel.vue'
import { useEngineStore } from '../../src/renderer/store/engine'

let episode
describe('预约上架失败不是已上架或未投稿', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    episode = { name: 'episode_failed', album_name: '星星布丁第6弹', path: 'E:/fixture',
      platform_status: '预约上架失败', published: true, complete: true, can_publish: true,
      can_shelf: true, stickers: [] }
    window.api = { send: vi.fn(async cmd => ({ status: 'ok', data:
      cmd === 'list_episodes' ? { episodes: [episode] } : cmd === 'list_series' ? { series: [] } : {} })),
      toFileUrl: p => `file://${p}`, onProgress: vi.fn(), onExit: vi.fn(),
      onRestarting: vi.fn(), onUpdateProgress: vi.fn() }
  })
  it.each([['预约上架失败', 'st-reject'], ['已预约上架', 'st-review'],
    ['已上架', 'st-live'], ['审核中', 'st-review'], ['强制下架', 'st-reject'],
    ['限制投稿', 'st-reject']])('%s 使用明确分级 %s', async (status, cls) => {
    episode.platform_status = status
    const wrapper = mount(EpisodesPanel)
    await flushPromises()
    expect(wrapper.get('.status-badge').classes()).toContain(cls)
    expect(wrapper.find('.shelf-btn').exists()).toBe(status === '预约上架失败')
    wrapper.unmount()
  })
  it('详情解释失败并阻止重新投稿，不误用旧驳回理由', async () => {
    episode.platform_reject_reason = '旧审核理由'
    useEngineStore().selectedEpisode = episode
    const wrapper = mount(EpisodeDetailPanel)
    await flushPromises()
    expect(wrapper.get('[data-test="shelf-failed"]').text()).toContain('不是审核驳回')
    expect(wrapper.get('[data-test="publish"]').element.disabled).toBe(true)
    expect(wrapper.text()).not.toContain('旧审核理由')
    expect(wrapper.text()).not.toContain('当前资源版本未验证完整')
    await wrapper.get('[data-test="publish"]').trigger('click')
    expect(window.api.send).not.toHaveBeenCalledWith('publish_episode', expect.anything())
    wrapper.unmount()
  })
})
