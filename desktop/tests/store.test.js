import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { validatePrefs, normalizePrefs } from '../src/renderer/store/engine'

// 2026-09-05 起（commit 9a0c752）：概率不足 100% 不再拦截保存，
// 由 normalizePrefs 按比例自动折算到 100%；validatePrefs 只拦真错误。
describe('mission preference validation', () => {
  it('accepts character probabilities below 100% (auto-folded on save)', () => {
    const prefs = {
      mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
      single_char_probs: { 甲: 0.2, 乙: 0.2 },
      base_probs: { 甲: { a: 1 }, 乙: { b: 1 } },
    }
    const characters = {
      甲: { bases: { a: '/a.png' } },
      乙: { bases: { b: '/b.png' } },
    }

    expect(validatePrefs(prefs, characters).ok).toBe(true)
    const { prefs: folded, adjusted } = normalizePrefs(prefs)
    expect(adjusted).toBe(true)
    expect(folded.single_char_probs.甲 + folded.single_char_probs.乙).toBeCloseTo(1)
  })

  it('folds a base probability group that does not total 100%', () => {
    const prefs = {
      mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
      single_char_probs: { 甲: 1 },
      base_probs: { 甲: { a: 0.2, b: 0.2 } },
    }
    const characters = {
      甲: { bases: { a: '/a.png', b: '/b.png' } },
    }

    expect(validatePrefs(prefs, characters).ok).toBe(true)
    const { prefs: folded, adjusted } = normalizePrefs(prefs)
    expect(adjusted).toBe(true)
    expect(folded.base_probs.甲.a).toBeCloseTo(0.5)
  })

  it('leaves already-normalized probabilities untouched', () => {
    const prefs = {
      mode_probs: { single: 0.5, duo: 0.5, trio: 0, quad: 0 },
      single_char_probs: { 甲: 1 },
      base_probs: { 甲: { a: 1 } },
    }
    expect(normalizePrefs(prefs).adjusted).toBe(false)
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
