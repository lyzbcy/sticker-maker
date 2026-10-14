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
    expect(send).toHaveBeenCalledWith('sync_platform_status', { fetch_reasons: false })
  })

  it('uses 弹 for counts rather than 单', async () => {
    EPISODES[0].platform_status = '审核通过'
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.get('.shelf-btn').text()).toContain('1 弹')
    expect(wrapper.text()).not.toMatch(/\d+ 单/)
    EPISODES[0].platform_status = '已上架'
    wrapper.unmount()
  })

  it.each([false, true])('预约上架结果与取消结果使用弹 cancelled=%s', async (cancelled) => {
    EPISODES[0].platform_status = '审核通过'
    const send = window.api.send
    send.mockImplementation(async (cmd) => {
      if (cmd === 'list_episodes') return { status: 'ok', data: { episodes: EPISODES } }
      if (cmd === 'list_series') return { status: 'ok', data: { series: [] } }
      if (cmd === 'shelf_passed') return { status: 'ok', data: {
        published: 1, cancelled, failed: [], remaining: cancelled ? ['其他作品'] : [],
      } }
      return { status: 'ok', data: {} }
    })
    const wrapper = mountPanel()
    try {
      await flushPromises()
      await wrapper.get('.shelf-btn').trigger('click')
      await flushPromises()
      expect(send).toHaveBeenCalledWith('shelf_passed', {})
      expect(wrapper.text()).toContain(cancelled ? '成功预约 1 弹' : '已预约上架 1 弹')
      expect(wrapper.text()).not.toMatch(/\d+ 单/)
      const store = useEngineStore()
      expect(store.activity.some(a => a.message.includes('1 弹'))).toBe(true)
    } finally {
      EPISODES[0].platform_status = '已上架'
      wrapper.unmount()
    }
  })

  it('快速上架结果显示待核对原因、剩余作品和状态保存告警', async () => {
    EPISODES[0].platform_status = '审核通过'
    window.api.send.mockImplementation(async cmd => {
      if (cmd === 'list_episodes') return { status: 'ok', data: { episodes: EPISODES } }
      if (cmd === 'list_series') return { status: 'ok', data: { series: [] } }
      if (cmd === 'shelf_passed') return { status: 'ok', data: {
        source: 'api', published: 1, cancelled: false,
        failed: [{ name: '作品2', reason: '预约结果待核对，未重复请求' }],
        remaining: ['作品3'], warnings: [{ message: '请同步平台状态' }],
      } }
      return { status: 'ok', data: {} }
    })
    const wrapper = mountPanel()
    try {
      await flushPromises()
      await wrapper.get('.shelf-btn').trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain('快速接口，已逐弹核验')
      expect(wrapper.text()).toContain('预约结果待核对，未重复请求')
      expect(wrapper.text()).toContain('剩余 1 弹未处理')
      expect(wrapper.text()).toContain('请同步平台状态')
    } finally {
      EPISODES[0].platform_status = '已上架'
      wrapper.unmount()
    }
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
