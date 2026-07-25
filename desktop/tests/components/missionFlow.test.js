import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

describe('mission flow components', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('offers one-click WeChat submission after generation', async () => {
    const send = vi.fn().mockResolvedValue({
      status: 'ok',
      data: { success: true, album_name: 'episode' },
    })
    Object.defineProperty(window, 'api', {
      configurable: true,
      value: { send, onProgress: vi.fn(), onRestarting: vi.fn() },
    })
    vi.resetModules()
    const { useEngineStore } = await import('../../src/renderer/store/engine')
    const ResultPreview = (
      await import('../../src/renderer/components/ResultPreview.vue')
    ).default
    const store = useEngineStore()
    store.lastEpisode = { episode_dir: '/tmp/episode', stickers: 16 }
    const wrapper = mount(ResultPreview)

    await wrapper.get('[data-test="publish"]').trigger('click')

    expect(send).toHaveBeenCalledWith(
      'publish_episode',
      { episode_dir: '/tmp/episode' },
    )
  })

  it('starts the loopback Agent service from the tools panel', async () => {
    const send = vi.fn(async (cmd) => {
      if (cmd === 'agent_status') {
        return { status: 'ok', data: { running: false, host: '127.0.0.1' } }
      }
      if (cmd === 'agent_prompt') {
        return { status: 'ok', data: { prompt: 'agent prompt' } }
      }
      if (cmd === 'agent_start') {
        return {
          status: 'ok',
          data: { running: true, host: '127.0.0.1', port: 7432, token: 'abc' },
        }
      }
      if (cmd === 'get_logs') return { status: 'ok', data: { logs: [] } }
      return { status: 'ok' }
    })
    Object.defineProperty(window, 'api', {
      configurable: true,
      value: { send, onProgress: vi.fn(), onRestarting: vi.fn() },
    })
    vi.resetModules()
    const ToolsPanel = (
      await import('../../src/renderer/components/ToolsPanel.vue')
    ).default
    const wrapper = mount(ToolsPanel)
    await new Promise(resolve => setTimeout(resolve, 0))

    await wrapper.get('[data-test="agent-start"]').trigger('click')

    expect(send).toHaveBeenCalledWith('agent_start', { port: 7432 })
  })
})
