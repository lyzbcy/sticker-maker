import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

let wrapper
async function setup(sendFeedback) {
  Object.defineProperty(window, 'api', { configurable: true, value: {
    send: vi.fn().mockResolvedValue({ status: 'ok', data: {} }),
    sendFeedback, copyText: vi.fn().mockResolvedValue({ ok: true }),
    onProgress: vi.fn(), onRestarting: vi.fn(),
  } })
  vi.resetModules()
  const FeedbackPanel = (await import('../../src/renderer/components/FeedbackPanel.vue')).default
  const { useEngineStore } = await import('../../src/renderer/store/engine')
  useEngineStore().activity = [{ stage: '测试', message: 'token=secret-sample-token' }]
  wrapper = mount(FeedbackPanel)
  await wrapper.get('textarea').setValue('测试反馈：请改善安装说明')
  const sendButton = () => wrapper.findAll('button').find(b => /发送给作者|发送中/.test(b.text()))
  return { sendButton }
}

describe('feedback interaction (mock transport; no actual messages)', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => wrapper?.unmount())

  it('confirms successful delivery and clears the message without leaving the page', async () => {
    const sendFeedback = vi.fn().mockResolvedValue({ ok: true })
    const { sendButton } = await setup(sendFeedback)
    await sendButton().trigger('click')
    await flushPromises()
    expect(sendFeedback).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="status"]').text()).toContain('已送达作者')
    expect(wrapper.get('textarea').element.value).toBe('')
    expect(sendButton().isDisabled()).toBe(true)
    expect(sendFeedback.mock.calls[0][0].logs).not.toContain('secret-sample-token')
  })

  it('keeps draft and restores send button after network rejection, allowing retry', async () => {
    const sendFeedback = vi.fn().mockRejectedValueOnce(new Error('模拟网络断开')).mockResolvedValueOnce({ ok: true })
    const { sendButton } = await setup(sendFeedback)
    await sendButton().trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('模拟网络断开')
    expect(wrapper.get('textarea').element.value).toContain('改善安装说明')
    expect(sendButton().isDisabled()).toBe(false)
    await sendButton().trigger('click')
    await flushPromises()
    expect(sendFeedback).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="status"]').text()).toContain('已送达作者')
  })

  it('deduplicates rapid double clicks while request remains pending', async () => {
    let resolveRequest
    const sendFeedback = vi.fn(() => new Promise(resolve => { resolveRequest = resolve }))
    const { sendButton } = await setup(sendFeedback)
    await sendButton().trigger('click')
    expect(sendButton().isDisabled()).toBe(true)
    await sendButton().trigger('click')
    expect(sendFeedback).toHaveBeenCalledTimes(1)
    resolveRequest({ ok: true })
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('已送达作者')
  })

  it('sends no diagnostics when fan opts out and offers copying on endpoint failure', async () => {
    const sendFeedback = vi.fn().mockResolvedValue({ ok: false, error: '模拟服务暂不可用' })
    const { sendButton } = await setup(sendFeedback)
    await wrapper.get('input[type="checkbox"]').setValue(false)
    await sendButton().trigger('click')
    await flushPromises()
    expect(sendFeedback.mock.calls[0][0].logs).toBe('')
    expect(wrapper.get('[role="status"]').text()).toContain('可以复制诊断信息')
    await wrapper.findAll('button').find(b => b.text() === '复制诊断信息').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('已复制')
  })
})
