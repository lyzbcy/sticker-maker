import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import EpisodesPanel from '../src/renderer/components/EpisodesPanel.vue'
import { useEngineStore } from '../src/renderer/store/engine'
import { estimateSync, recordSyncTiming } from '../src/renderer/utils/syncEstimate'

describe('sync options', () => {
  let pinia, store, send
  beforeEach(() => {
    localStorage.clear()
    pinia = createPinia()
    setActivePinia(pinia)
    send = vi.fn().mockResolvedValue({ status: 'ok', data: {
      source: 'api', complete: true, updated: 605, reasons_fetched: 0,
      reasons_skipped: 0, reason_seconds: 0,
    } })
    window.api = { send, stop: vi.fn().mockResolvedValue(), onProgress: vi.fn(), onRestarting: vi.fn() }
    store = useEngineStore()
    vi.spyOn(store, 'loadEpisodes').mockResolvedValue()
    vi.spyOn(store, 'loadSeries').mockResolvedValue()
  })
  const mountPanel = () => mount(EpisodesPanel, { global: { plugins: [pinia] } })

  it('defaults to fast mode with estimates and the recommended usage', async () => {
    const wrapper = mountPanel()
    expect(wrapper.get('input[type=checkbox]').element.checked).toBe(false)
    expect(wrapper.text()).toContain('不勾选：仅更新状态与统计，预计')
    expect(wrapper.text()).toContain('勾选：同时补录驳回理由，预计')
    expect(wrapper.text()).toContain('平常更新状态、准备一键上架，建议不勾选')
    await wrapper.get('.sync-btn').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('sync_platform_status', { fetch_reasons: false })
    expect(wrapper.get('.sync-summary').text()).toContain('605')
    expect(wrapper.get('.sync-summary').text()).toContain('接口直读')
    wrapper.unmount()
  })

  it('checked mode explicitly requests reasons', async () => {
    const wrapper = mountPanel()
    await wrapper.get('input[type=checkbox]').setValue(true)
    await wrapper.get('.sync-btn').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('sync_platform_status', { fetch_reasons: true })
    wrapper.unmount()
  })

  it('disables option changes and duplicate sync while a request is pending', async () => {
    let finish
    send.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const wrapper = mountPanel()
    await wrapper.get('.sync-btn').trigger('click')
    expect(wrapper.get('.sync-btn').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input[type=checkbox]').attributes('disabled')).toBeDefined()
    await wrapper.get('.cancel-btn').trigger('click')
    expect(window.api.stop).toHaveBeenCalledOnce()
    finish({ status: 'ok', data: { cancelled: true, updated: 3 } })
    await flushPromises()
    expect(wrapper.get('.sync-summary').text()).toContain('已取消')
    wrapper.unmount()
  })

  it('shows partial results rather than a false success', async () => {
    send.mockResolvedValue({ status: 'ok', data: { source: 'api', complete: false,
      updated: 604, unknown_statuses: [{ status_code: 99 }], reason_failures: [{ name: 'x' }] } })
    const wrapper = mountPanel()
    await wrapper.get('.sync-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('.sync-summary').text()).toContain('部分同步')
    expect(wrapper.get('.sync-summary').text()).toContain('1 弹为平台新状态')
    expect(wrapper.get('.sync-summary').text()).toContain('1 弹理由读取失败')
    wrapper.unmount()
  })
})

describe('estimates', () => {
  it('counts only uncached rejection reasons and learns measured timings', () => {
    const episodes = Array.from({ length: 129 }, () => ({ platform_status: '未通过审核' }))
    const first = estimateSync(episodes)
    expect(first.pending).toBe(129)
    expect(first.fast).not.toBe(first.withReasons)
    episodes[0] = { platform_status: '未通过审核', platform_reject_reason: 'reason',
      platform_review_cycle: 'one', platform_reject_checked_cycle: 'one' }
    const history = recordSyncTiming({ source: 'api', reason_seconds: 15, reasons_fetched: 30 }, 25)
    expect(history).toEqual({ baseSeconds: 10, perReasonSeconds: .5 })
    expect(estimateSync(episodes, history).pending).toBe(128)
    expect(estimateSync(episodes, history).measured).toBe(true)
  })

  it('does not learn cancelled/fallback durations', () => {
    const old = { baseSeconds: 10 }
    expect(recordSyncTiming({ source: 'api', cancelled: true }, 100, old)).toBe(old)
    expect(recordSyncTiming({ source: 'dom' }, 100, old)).toBe(old)
  })
})
