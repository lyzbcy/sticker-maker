import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

const prefs = () => ({ mode_probs: { single: 1 }, single_char_probs: { 示例: 1 }, base_probs: { 示例: { a: 1 } }, grid_size: 4 })
const mounted = []
async function setup(component, handler = async () => ({ status: 'ok', data: {} })) {
  const send = vi.fn(handler)
  Object.defineProperty(window, 'api', { configurable: true, value: {
    send, onProgress: vi.fn(), onRestarting: vi.fn(), onExit: vi.fn(), onUpdateProgress: vi.fn(),
  } })
  vi.resetModules()
  const { useEngineStore } = await import('../../src/renderer/store/engine')
  const store = useEngineStore()
  store.prefs = prefs()
  store.characters = { 示例: { bases: { a: '/a.png' } } }
  const modules = import.meta.glob('../../src/renderer/components/*.vue')
  const Component = (await modules[`../../src/renderer/components/${component}.vue`]()).default
  const wrapper = mount(Component)
  mounted.push(wrapper)
  await flushPromises()
  return { send, store, wrapper }
}

describe('fan first-use regression (isolated IPC fixtures, not actual Codex/publish)', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })

  it('does not recommend adjusting probabilities for a disk save failure', async () => {
    const { wrapper, store } = await setup('Wizard', async cmd => {
      if (cmd === 'check_codex') return { status: 'ok', data: { image_ready: true } }
      if (cmd === 'list_characters') return { status: 'ok', data: { characters: { 示例: { bases: { a: '/a.png' } } } } }
      if (cmd === 'save_prefs') return { status: 'error', errors: [{ message: '磁盘写入失败，请释放空间' }] }
      return { status: 'ok', data: {} }
    })
    store.phase = 'wizard'
    for (let i = 0; i < 4; i++) { await wrapper.get('.btn-primary').trigger('click'); await flushPromises() }
    await wrapper.get('.btn-finish').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('磁盘写入失败')
    expect(wrapper.text()).not.toContain('总和调整到 100%')
    expect(store.phase).toBe('wizard')
    expect(wrapper.get('.btn-finish').isDisabled()).toBe(false)
  })

  it('requires fans to opt into automatic platform publishing', async () => {
    const { wrapper } = await setup('MainScreen')
    const autoPublish = wrapper.findAll('input[type="checkbox"]').find(w => w.element.parentElement.textContent.includes('完成后自动发布'))
    expect(autoPublish).toBeTruthy()
    expect(autoPublish.element.checked).toBe(false)
  })

  it('shows login rather than reinstall when Codex is installed but logged out', async () => {
    const { wrapper } = await setup('WizardStepCodex', async () => ({ status: 'ok', data: {
      installed: true, logged_in: false, image_ready: false, guidance_msg: 'codex 已安装，请先登录',
    } }))
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).not.toContain('一键安装 codex')
    expect(wrapper.findAll('button').some(w => /登录/.test(w.text()))).toBe(true)
  })

  it('preserves engine startup failure as visible actionable feedback', async () => {
    const { store } = await setup('MainScreen', async cmd => {
      if (cmd === 'load_prefs') throw new Error('测试：引擎启动失败')
      return { status: 'ok', data: {} }
    })
    await store.init()
    expect(store.phase).toBe('main')
    expect(store.prefs.grid_size).toBe(4)
    expect(store.lastError?.map(e => e.message).join(' ')).toMatch(/引擎|启动|重试/)
  })

  it('does not claim installation is running before a missing-tool fan clicks install', async () => {
    const { wrapper } = await setup('WizardStepCodex', async () => ({ status: 'ok', data: {
      installed: false, logged_in: false, image_ready: false,
    } }))
    expect(wrapper.text()).toContain('一键安装 codex')
    expect(wrapper.text()).not.toContain('正在安装，请稍候')
  })

  it('offers repair without claiming a repair is already running', async () => {
    const { wrapper, store } = await setup('WizardStepCodex', async () => ({ status: 'ok', data: {
      installed: true, logged_in: false, image_ready: false, needs_repair: true,
      guidance_msg: '生图运行组件缺失，请点击修复生图工具。',
    } }))
    expect(wrapper.findAll('button').some(b => b.text() === '修复生图工具')).toBe(true)
    expect(wrapper.text()).not.toContain('正在安装，请稍候')
    store.installing = true
    store.installLog = ['下载运行组件 30%']
    await flushPromises()
    expect(wrapper.text()).toContain('正在安装，请稍候')
    expect(wrapper.text()).toContain('下载运行组件 30%')
    expect(wrapper.findAll('button').some(b => b.text() === '修复生图工具')).toBe(false)
  })
})
