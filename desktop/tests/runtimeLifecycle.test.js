import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

let handlers, store, wrapper, api
const eventNames = ['onTask', 'onProgress', 'onExit', 'onRestarting', 'onUpdateProgress']
function emit(name, event) { for (const fn of [...handlers[name]]) fn(event) }
async function setup() {
  const { useEngineStore } = await import('../src/renderer/store/engine')
  store = useEngineStore()
  const { default: StatusBar } = await import('../src/renderer/components/StatusBar.vue')
  wrapper = mount(StatusBar)
}
beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  setActivePinia(createPinia())
  handlers = Object.fromEntries(eventNames.map(name => [name, new Set()]))
  api = { send: vi.fn(), recordActivity: vi.fn().mockResolvedValue({ ok: true }) }
  for (const name of eventNames) api[name] = fn => {
    handlers[name].add(fn)
    return () => handlers[name].delete(fn)
  }
  Object.defineProperty(window, 'api', { configurable: true, value: api })
})
afterEach(() => {
  wrapper?.unmount(); wrapper = null
  store?.$dispose(); store = null
  vi.useRealTimers()
})
describe('engine event lifetime and task status', () => {
  it('returns to idle after completed resource work without deleting activity history', async () => {
    await setup()
    emit('onTask', { id: 'library', state: 'start', startedAt: 1, message: '读取资源' })
    emit('onProgress', { stage: 'prepare', message: '正在对齐共享资源 881/881' })
    emit('onTask', { id: 'library', state: 'end' })
    await nextTick()
    expect(wrapper.find('.status-text').text()).toBe('就绪 · 引擎待命')
    expect(store.activity.at(-1).message).toBe('正在对齐共享资源 881/881')
  })
  it('keeps another concurrent task visible when one completes', async () => {
    await setup()
    emit('onTask', { id: 'a', state: 'start', startedAt: 1, message: '任务A' })
    emit('onTask', { id: 'b', state: 'start', startedAt: 2, message: '任务B' })
    emit('onTask', { id: 'a', state: 'end' })
    await nextTick()
    expect(wrapper.find('.status-text').text()).toBe('任务B')
    expect(wrapper.find('.dot').classes()).toContain('run')
  })
  it('clears busy flags, task map and progress when an engine exits', async () => {
    await setup()
    store.running = store.publishing = store.installing = true
    store.progress = store.publishProgress = { message: '等待' }
    emit('onTask', { id: 'a', state: 'start', startedAt: 1 })
    emit('onExit', { code: 2 })
    expect(store.running).toBe(false)
    expect(store.publishing).toBe(false)
    expect(store.installing).toBe(false)
    expect(store.activeTasks).toEqual({})
    expect(store.progress).toBeNull()
    expect(store.publishProgress).toBeNull()
    expect(store.lastError[0].message).toContain('引擎')
  })
  it('clears all pending visual state during restart without retrying work', async () => {
    await setup()
    store.running = store.publishing = store.installing = true
    emit('onTask', { id: 'a', state: 'start', startedAt: 1 })
    emit('onRestarting', {})
    expect(store.activeTasks).toEqual({})
    expect([store.running, store.publishing, store.installing]).toEqual([false, false, false])
    expect(api.send).not.toHaveBeenCalled()
  })
  it('retains the singleton refusal and stops stale running indicators', async () => {
    await setup()
    emit('onTask', { id: 'a', state: 'start', startedAt: 1 })
    emit('onExit', { code: 3 })
    expect(store.lastError[0].message).toContain('另一个')
    expect(store.activeTasks).toEqual({})
    expect(api.send).not.toHaveBeenCalled()
  })
  it('unsubscribes all five IPC listeners when the store scope is disposed', async () => {
    await setup()
    expect(eventNames.map(name => handlers[name].size)).toEqual([1, 1, 1, 1, 1])
    store.$dispose()
    expect(eventNames.map(name => handlers[name].size)).toEqual([0, 0, 0, 0, 0])
  })
  it('ignores callbacks already queued before disposal', async () => {
    await setup()
    const progress = [...handlers.onProgress][0], task = [...handlers.onTask][0]
    store.$dispose()
    progress({ stage: 'late', message: 'late callback' })
    task({ id: 'late', state: 'start' })
    expect(store.activity).toEqual([])
    expect(store.activeTasks).toEqual({})
  })
  it('keeps the bounded sixty-entry activity stream and persistence opt-out', async () => {
    await setup()
    for (let i = 0; i < 70; i++) emit('onProgress', { stage: 'prepare', message: String(i) })
    expect(store.activity).toHaveLength(60)
    expect(store.activity[0].message).toBe('10')
    expect(api.recordActivity).not.toHaveBeenCalled()
  })
  it('keeps update progress visible after a completed engine task', async () => {
    await setup()
    emit('onTask', { id: 'a', state: 'end' })
    emit('onUpdateProgress', { stage: 'download', version: '0.7.0', percent: 25, receivedMB: '1', totalMB: '4' })
    await nextTick()
    expect(wrapper.find('.status-text').text()).toContain('正在下载 0.7.0')
    expect(wrapper.find('.status-text').text()).toContain('25%')
  })
  it('can show a new explicit activity after the prior task settled', async () => {
    await setup()
    emit('onTask', { id: 'a', state: 'end' })
    store.pushActivity({ stage: 'RUN', message: '批量完成：生成 1/1 组' })
    await nextTick()
    expect(wrapper.find('.status-text').text()).toContain('批量完成')
  })
})
