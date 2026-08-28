import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import EpisodesPanel from '../../src/renderer/components/EpisodesPanel.vue'
import { useEngineStore } from '../../src/renderer/store/engine'

const EPISODES = [
  {
    name: 'episode_20260827_205842', path: 'E:/eps/episode_20260827_205842',
    sticker_count: 16, cover: 'E:/eps/episode_20260827_205842/封面/封面.png',
    album_name: '周三涵做表情 63', series_id: 's1', series_name: '周三涵做表情',
    number: 63, published: true, complete: true,
    platform_status: '已上架', platform_downloads: '68',
    platform_sends: '214', platform_tips: '-', platform_updated_at: '2026-08-27 23:59:00',
  },
  {
    name: 'episode_20260827_232324', path: 'E:/eps/episode_20260827_232324',
    sticker_count: 16, cover: '', album_name: '', series_id: '', series_name: '',
    number: null, published: false, complete: true,
    platform_status: '', platform_downloads: '-', platform_sends: '-',
    platform_tips: '-', platform_updated_at: '',
  },
]

function mountPanel() {
  return mount(EpisodesPanel, {
    global: { stubs: { teleport: true } },
  })
}

describe('作品库微信风表格', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // 直接挂 window.api（不要 stubGlobal 整个 window，会破坏 happy-dom 事件构造器）
    window.api = {
      send: vi.fn(async (cmd) => {
        if (cmd === 'list_episodes') return { status: 'ok', data: { episodes: EPISODES } }
        if (cmd === 'list_series') return { status: 'ok', data: { series: [] } }
        return { status: 'ok', data: {} }
      }),
      toFileUrl: (p) => `file://${p}`,
      onProgress: () => {},
      onExit: () => {},
      onRestarting: () => {},
      onUpdateProgress: () => {},
    }
  })

  it('一行一个作品，渲染表头与数据行', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const heads = wrapper.findAll('thead th').map(h => h.text())
    expect(heads).toEqual(['作品', '下载次数', '发送次数', '赞赏金额', '状态', '最后更新', '操作'])
    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    // 第一行：作品名 + 平台数据
    expect(rows[0].text()).toContain('周三涵做表情 63')
    expect(rows[0].text()).toContain('68')
    expect(rows[0].text()).toContain('已上架')
    // 第二行：未同步作品显示本地态
    expect(rows[1].text()).toContain('未提交')
  })

  it('状态徽章分级：已上架绿/待审核黄/未提交黄标', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const badge1 = wrapper.findAll('tbody tr')[0].find('.status-badge')
    expect(badge1.classes()).toContain('st-live')
  })

  it('一键更新：调 sync_platform_status 并刷新列表', async () => {
    const send = window.api.send
    const wrapper = mountPanel()
    await flushPromises()
    send.mockClear()
    await wrapper.find('.sync-btn').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('sync_platform_status')
  })

  it('删除：先确认再物理删除', async () => {
    const send = window.api.send
    const wrapper = mountPanel()
    await flushPromises()
    send.mockClear()
    const row = wrapper.findAll('tbody tr')[1]
    // 第一次点删除 → 只出现确认按钮，不触发命令
    await row.find('.op-btn.del').trigger('click')
    expect(send).not.toHaveBeenCalled()
    // 点确认 → delete_episode
    await row.find('.op-btn.del.sure').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('delete_episode',
      { episode_dir: 'E:/eps/episode_20260827_232324' })
  })
})
