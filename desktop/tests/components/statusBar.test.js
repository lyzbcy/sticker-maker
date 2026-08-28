import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

function mockApi() {
  const handlers = []
  Object.defineProperty(window, 'api', {
    configurable: true,
    value: {
      send: vi.fn(async () => ({ status: 'ok', data: {} })),
      onProgress: (cb) => handlers.push(cb),
      onRestarting: vi.fn(),
    },
  })
  return handlers
}

async function mountBar() {
  const { useEngineStore } = await import('../../src/renderer/store/engine')
  const StatusBar = (
    await import('../../src/renderer/components/StatusBar.vue')
  ).default
  const store = useEngineStore()
  store.phase = 'main'
  const wrapper = mount(StatusBar)
  return { wrapper, store }
}

describe('StatusBar bottom bar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetModules()
  })

  it('shows the latest progress message while running', async () => {
    const handlers = mockApi()
    const { wrapper, store } = await mountBar()

    store.running = true
    await flushPromises()
    handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: '等待 codex 响应… 已等 45s', percent: 0.25 }))
    await flushPromises()

    expect(wrapper.get('.status-text').text()).toContain('等待 codex 响应… 已等 45s')
    expect(wrapper.get('.dot').classes()).toContain('run')
  })

  it('expands the activity log panel on click showing full history', async () => {
    const handlers = mockApi()
    const { wrapper } = await mountBar()

    handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: '生成模式已选定：故事模式', percent: 0.25 }))
    handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: '输入就绪：prompt 312 字 · 参考图 1 张', percent: 0.25 }))

    expect(wrapper.find('.activity-panel').exists()).toBe(false)
    await wrapper.get('.bar').trigger('click')
    expect(wrapper.find('.activity-panel').exists()).toBe(true)

    const rows = wrapper.findAll('.activity-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('生成模式已选定')
    expect(rows[1].text()).toContain('输入就绪：prompt 312 字')
  })

  it('marks failure and success rows with distinct styles', async () => {
    const handlers = mockApi()
    const { wrapper } = await mountBar()
    handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: 'codex 生图失败：超时', percent: 0.25 }))
    handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: '输出就绪：grid_4x4.png', percent: 0.25 }))
    await wrapper.get('.bar').trigger('click')

    const rows = wrapper.findAll('.activity-row')
    expect(rows[0].classes()).toContain('bad')
    expect(rows[1].classes()).toContain('good')
  })

  it('shows ready state with green dot when idle', async () => {
    mockApi()
    const { wrapper, store } = await mountBar()
    store.running = false
    store.lastError = null
    expect(wrapper.get('.status-text').text()).toContain('就绪')
    expect(wrapper.get('.dot').classes()).toContain('ok')
  })

  it('caps the activity log at 60 entries', async () => {
    const handlers = mockApi()
    const { store } = await mountBar()
    for (let i = 0; i < 80; i++) {
      handlers.forEach(cb => cb({ stage: 'S1', phase: 'stage_progress', message: `msg-${i}`, percent: 0.25 }))
    }
    expect(store.activity.length).toBe(60)
    expect(store.activity[store.activity.length - 1].message).toBe('msg-79')
    expect(store.activity[0].message).toBe('msg-20')
  })
})
