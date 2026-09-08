import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
// 模拟 Electron IPC 的 structured clone：V8 序列化器和 Electron 一样拒绝 Proxy
import { serialize } from 'node:v8'

const READY_PREFS = {
  mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
  single_char_probs: { 星星布丁: 1 },
  base_probs: { 星星布丁: { a: 1 } },
  grid_size: 4,
  transparent_default: true,
  ref_lib_priority: true,
  story_mode: true,
}
const CHARACTERS = { 星星布丁: { bases: { a: '/a.png' } } }

async function setupWizard(savePrefsResult) {
  const send = vi.fn(async (cmd, args) => {
    if (cmd === 'check_codex') {
      return { status: 'ok', data: { image_ready: true, installed: true } }
    }
    if (cmd === 'list_characters') {
      return { status: 'ok', data: { characters: CHARACTERS } }
    }
    if (cmd === 'save_prefs') {
      // 和真实 ipcRenderer.invoke 一致：无法序列化的参数直接抛错
      try {
        serialize(args)
      } catch (e) {
        throw new Error('An object could not be cloned.')
      }
      return savePrefsResult
    }
    return { status: 'ok', data: {} }
  })
  Object.defineProperty(window, 'api', {
    configurable: true,
    value: { send, onProgress: vi.fn(), onRestarting: vi.fn() },
  })
  vi.resetModules()
  const { useEngineStore } = await import('../../src/renderer/store/engine')
  const Wizard = (
    await import('../../src/renderer/components/Wizard.vue')
  ).default
  const store = useEngineStore()
  store.prefs = JSON.parse(JSON.stringify(READY_PREFS))
  store.characters = CHARACTERS
  store.phase = 'wizard'
  const wrapper = mount(Wizard)
  await flushPromises()
  // 等第一步的 check_codex 完成后，连点“下一步”推进到第 5 步（生图偏好）
  for (let i = 0; i < 4; i++) {
    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()
  }
  return { wrapper, store, send }
}

describe('wizard finish button', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('finishes with below-100% probabilities (auto-folded, no blocking)', async () => {
    const { wrapper, store, send } = await setupWizard({ status: 'ok' })
    // 已到达第 5 步：完成按钮可见
    const finishBtn = wrapper.get('.btn-finish')
    expect(finishBtn.text()).toBe('完成')

    // 2026-09-05 起（commit 9a0c752）：概率不足 100% 不再拦截，保存时自动折算
    store.prefs.single_char_probs.星星布丁 = 0.7
    await finishBtn.trigger('click')
    await flushPromises()

    // 不拦截：正常保存并进入主界面
    expect(send).toHaveBeenCalledWith('save_prefs', expect.anything())
    expect(store.phase).toBe('main')
  })

  it('shows a backend error when save_prefs fails', async () => {
    const { wrapper, store } = await setupWizard({ status: 'error' })

    await wrapper.get('.btn-finish').trigger('click')
    await flushPromises()

    const errorBox = wrapper.find('.finish-error')
    expect(errorBox.exists()).toBe(true)
    expect(errorBox.text()).toContain('保存失败')
    // 失败后停留在向导，不会切到主界面
    expect(store.phase).toBe('wizard')
  })

  it('navigates to main screen when finishing succeeds', async () => {
    const { wrapper, store } = await setupWizard({ status: 'ok' })

    await wrapper.get('.btn-finish').trigger('click')
    await flushPromises()

    expect(wrapper.find('.finish-error').exists()).toBe(false)
    expect(store.phase).toBe('main')
  })
})
