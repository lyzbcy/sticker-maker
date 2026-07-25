import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { validatePrefs } from '../src/renderer/store/engine'

describe('mission preference validation', () => {
  it('rejects character probabilities that do not total 100%', () => {
    const prefs = {
      mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
      single_char_probs: { 甲: 0.2, 乙: 0.2 },
      base_probs: { 甲: { a: 1 }, 乙: { b: 1 } },
    }
    const characters = {
      甲: { bases: { a: '/a.png' } },
      乙: { bases: { b: '/b.png' } },
    }

    const result = validatePrefs(prefs, characters)

    expect(result.ok).toBe(false)
    expect(result.message).toContain('角色概率')
  })

  it('rejects a base probability group that does not total 100%', () => {
    const prefs = {
      mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
      single_char_probs: { 甲: 1 },
      base_probs: { 甲: { a: 0.2, b: 0.2 } },
    }
    const characters = {
      甲: { bases: { a: '/a.png', b: '/b.png' } },
    }

    const result = validatePrefs(prefs, characters)

    expect(result.ok).toBe(false)
    expect(result.message).toContain('甲')
    expect(result.message).toContain('base')
  })
})

describe('desktop publish action', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('publishes the selected episode through the engine bridge', async () => {
    const send = vi.fn().mockResolvedValue({
      status: 'ok',
      data: { success: true, album_name: '一弹' },
    })
    Object.defineProperty(window, 'api', {
      configurable: true,
      value: { send, onProgress: vi.fn(), onRestarting: vi.fn() },
    })
    vi.resetModules()
    const { useEngineStore } = await import('../src/renderer/store/engine')
    const store = useEngineStore()

    const ok = await store.publishEpisode('/tmp/episode')

    expect(ok).toBe(true)
    expect(send).toHaveBeenCalledWith(
      'publish_episode',
      { episode_dir: '/tmp/episode' },
    )
  })
})
