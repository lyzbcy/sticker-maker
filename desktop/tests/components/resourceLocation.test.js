import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ResourceLocationPanel from '../../src/renderer/components/ResourceLocationPanel.vue'

const candidate = { path: 'D:/表情/工程', library_id: 'library', storage_mode: 'projects', accounts: [{ account_id: 'owner', account_label: '作品账号' }] }
beforeEach(() => {
  setActivePinia(createPinia())
  window.api = { onProgress: vi.fn(), onRestarting: vi.fn(), onExit: vi.fn(), selectDirectory: vi.fn(async () => ({ canceled: false, path: 'D:/表情' })),
    send: vi.fn(async cmd => ({ status: 'ok', data: cmd === 'project_location_inspect' ? { candidates: [candidate] } : {} })) }
})
describe('资源位置入口', () => {
  it('空配置主页直接展示选择入口，识别后仍需确认账号', async () => {
    const w = mount(ResourceLocationPanel, { props: { compact: true } }); await flushPromises()
    expect(w.text()).toContain('选择已有表情资源')
    await w.get('[data-test=choose-resource-location]').trigger('click'); await flushPromises()
    expect(window.api.send).toHaveBeenCalledWith('project_location_inspect', { path: 'D:/表情' })
    expect(w.text()).toContain('直接读取工程文件夹')
    expect(w.get('[data-test=connect-resource-location]').element.disabled).toBe(true)
    await w.get('[data-test=location-confirm]').setValue(true)
    await w.get('[data-test=connect-resource-location]').trigger('click'); await flushPromises()
    expect(window.api.send).toHaveBeenCalledWith('project_location_connect', { path: candidate.path, library_id: 'library', account_id: 'owner', confirm_account: true })
    expect(w.emitted('changed')).toHaveLength(1)
  })
  it('取消重新选择会清除之前的候选，不连接旧路径', async () => {
    const w = mount(ResourceLocationPanel); await flushPromises()
    await w.get('[data-test=choose-resource-location]').trigger('click'); await flushPromises()
    window.api.selectDirectory.mockResolvedValue({ canceled: true })
    await w.get('[data-test=choose-resource-location]').trigger('click'); await flushPromises()
    expect(w.find('[data-test=connect-resource-location]').exists()).toBe(false)
    expect(window.api.send).not.toHaveBeenCalledWith('project_location_connect', expect.anything())
  })
  it('多个库和账号由用户选择，不默认认领第一个账号', async () => {
    window.api.send.mockResolvedValue({ status: 'ok', data: { candidates: [candidate, { ...candidate, path: 'D:/另一库', accounts: [...candidate.accounts, { account_id: 'other', account_label: '另一个账号' }] }] } })
    const w = mount(ResourceLocationPanel); await flushPromises()
    await w.get('[data-test=choose-resource-location]').trigger('click'); await flushPromises()
    await w.get('[data-test=location-confirm]').setValue(true)
    await w.get('[data-test=location-candidate]').setValue('D:/另一库')
    expect(w.get('[data-test=location-confirm]').element.checked).toBe(false)
    expect(w.get('[data-test=location-account]').element.value).toBe('')
  })
  it('已连接时主页隐藏入口，离线时保留找回入口', async () => {
    window.api.send.mockResolvedValue({ status: 'ok', data: { connected: true } })
    const w = mount(ResourceLocationPanel, { props: { compact: true } }); await flushPromises()
    expect(w.find('[data-test=resource-location]').exists()).toBe(false)
    window.api.send.mockResolvedValue({ status: 'ok', data: { connected: true, offline: true } })
    const offline = mount(ResourceLocationPanel, { props: { compact: true } }); await flushPromises()
    expect(offline.text()).toContain('资源位置暂不可用')
  })
})
