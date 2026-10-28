import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

let wrapper, api, store
async function setup() {
  const { useEngineStore } = await import('../src/renderer/store/engine')
  const FeedbackPanel = (await import('../src/renderer/components/FeedbackPanel.vue')).default
  store = useEngineStore()
  store.activity = [{ stage: 'prepare', message: 'LOCAL-DIAGNOSTIC-SAMPLE token=secret-sample-token' }]
  wrapper = mount(FeedbackPanel)
  await wrapper.get('textarea').setValue('改善设置页说明')
}
const copyButton = () => wrapper.findAll('button').find(b => b.text() === '复制诊断信息')
beforeEach(() => {
  vi.resetModules(); setActivePinia(createPinia())
  api = { send: vi.fn(), onProgress: vi.fn(), onRestarting: vi.fn(), copyText: vi.fn().mockResolvedValue({ ok: true }), sendFeedback: vi.fn() }
  Object.defineProperty(window, 'api', { configurable: true, value: api })
})
afterEach(() => { wrapper?.unmount(); store?.$dispose() })
describe('feedback clipboard follows the same log choice as sending', () => {
  it('omits diagnostic history after logs are unchecked, preserving draft', async () => {
    await setup()
    await wrapper.get('input[type=checkbox]').setValue(false)
    await copyButton().trigger('click'); await flushPromises()
    expect(api.copyText.mock.calls[0][0]).toContain('改善设置页说明')
    expect(api.copyText.mock.calls[0][0]).not.toContain('LOCAL-DIAGNOSTIC-SAMPLE')
    expect(wrapper.get('textarea').element.value).toBe('改善设置页说明')
    expect(api.sendFeedback).not.toHaveBeenCalled()
  })
  it('includes redacted diagnostics only when selected', async () => {
    await setup(); await copyButton().trigger('click'); await flushPromises()
    expect(api.copyText.mock.calls[0][0]).toContain('LOCAL-DIAGNOSTIC-SAMPLE')
    expect(api.copyText.mock.calls[0][0]).not.toContain('secret-sample-token')
    expect(wrapper.get('[role=status]').text()).toContain('已复制')
  })
  it('shows clipboard rejection, keeps draft and permits retry', async () => {
    await setup()
    api.copyText.mockRejectedValueOnce(new Error('clipboard unavailable'))
    await expect(wrapper.vm.copy()).resolves.toBeUndefined()
    await flushPromises()
    expect(wrapper.get('[role=status]').text()).toContain('复制未完成')
    expect(wrapper.get('textarea').element.value).toBe('改善设置页说明')
    expect(copyButton().isDisabled()).toBe(false)
    await copyButton().trigger('click'); await flushPromises()
    expect(wrapper.get('[role=status]').text()).toContain('已复制')
  })
  it('makes clipboard copy single-flight while a response is pending', async () => {
    await setup()
    let resolve
    api.copyText.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    await copyButton().trigger('click')
    expect(copyButton().isDisabled()).toBe(true)
    await copyButton().trigger('click')
    expect(api.copyText).toHaveBeenCalledTimes(1)
    resolve({ ok: true }); await flushPromises()
    expect(copyButton().isDisabled()).toBe(false)
  })
})
