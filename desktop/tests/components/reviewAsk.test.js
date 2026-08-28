import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useEngineStore } from '../../src/renderer/store/engine'

const DAY = 24 * 60 * 60 * 1000

describe('求好评门控 shouldAskForReview（prompt「不打扰用户的求好评」）', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('发布不足 2 次不打扰', () => {
    const s = useEngineStore()
    expect(s.shouldAskForReview(0, 0)).toBe(false)
    expect(s.shouldAskForReview(1, 0)).toBe(false)
  })

  it('发布 ≥2 次且从未问过 → 弹', () => {
    const s = useEngineStore()
    expect(s.shouldAskForReview(2, 0)).toBe(true)
    expect(s.shouldAskForReview(5, 0)).toBe(true)
  })

  it('15 天内问过 → 不弹', () => {
    const s = useEngineStore()
    const now = Date.now()
    expect(s.shouldAskForReview(3, now - 14 * DAY, now)).toBe(false)
    expect(s.shouldAskForReview(3, now - 1, now)).toBe(false)
  })

  it('超过 15 天 → 可以再弹', () => {
    const s = useEngineStore()
    const now = Date.now()
    expect(s.shouldAskForReview(3, now - 16 * DAY, now)).toBe(true)
    expect(s.shouldAskForReview(3, now - 15.1 * DAY, now)).toBe(true)
  })

  it('边界：恰好 15 天整 → 冷却结束，可再弹', () => {
    const s = useEngineStore()
    const now = Date.now()
    expect(s.shouldAskForReview(3, now - 15 * DAY, now)).toBe(true)
    expect(s.shouldAskForReview(3, now - (15 * DAY - 1), now)).toBe(false)
  })
})
