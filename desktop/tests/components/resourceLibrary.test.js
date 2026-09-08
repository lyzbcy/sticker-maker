import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ResourceLibraryPanel from '../../src/renderer/components/ResourceLibraryPanel.vue'
import EpisodesPanel from '../../src/renderer/components/EpisodesPanel.vue'
import EpisodeDetailPanel from '../../src/renderer/components/EpisodeDetailPanel.vue'
import SettingsPanel from '../../src/renderer/components/SettingsPanel.vue'
import { useEngineStore } from '../../src/renderer/store/engine'

const status = (overrides = {}) => ({
  connected: false,
  root: '',
  library_id: '',
  account_id: '',
  account_label: '',
  accounts: [],
  counts: { available: 0, placeholder: 0, pending: 0, conflict: 0, deleted: 0 },
  tasks: [],
  conflicts: [],
  ...overrides,
})

function apiFor(handler = () => ({ status: 'ok', data: {} })) {
  const send = vi.fn(async (cmd, args) => handler(cmd, args))
  window.api = {
    send,
    selectDirectory: vi.fn(async () => '/Volumes/share/sticker-library'),
    toFileUrl: p => `file://${p}`,
    stop: vi.fn(),
    onProgress: vi.fn(),
    onRestarting: vi.fn(),
  }
  return send
}

describe('账号与资源库面板', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('先展示扫描预览，且迁移清理默认关闭；有缺失资源时阻止执行', async () => {
    let previewCount = 0
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_preview') {
        previewCount += 1
        return {
          status: 'ok',
          data: {
            plan_id: `plan-${previewCount}`,
            mode: 'migration',
            target: '/Volumes/share/sticker-library',
            entries: [{ path: '作品/原图.png', size: 1024 }],
            missing: previewCount === 1 ? ['外部/base.png'] : [],
            bytes: 1024,
          },
        }
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()

    await wrapper.get('[data-test="export-target"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="mode-migration"]').setValue()
    expect(wrapper.get('[data-test="cleanup"]').element.checked).toBe(false)
    await wrapper.get('[data-test="preview-export"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_preview', {
      target: '/Volumes/share/sticker-library', mode: 'migration', cleanup: false,
    })
    expect(wrapper.text()).toContain('缺失')
    expect(wrapper.get('[data-test="execute-export"]').element.disabled).toBe(true)
    expect(send).not.toHaveBeenCalledWith('library_execute', expect.anything())

    await wrapper.get('[data-test="preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="execute-export"]').element.disabled).toBe(false)
    await wrapper.get('[data-test="execute-export"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_execute', { plan_id: 'plan-2' })
  })

  it('切换导出模式或清理选项会使旧预览失效', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_preview') {
        return {
          status: 'ok',
          data: {
            plan_id: 'plan-current', mode: 'backup', target: '/Volumes/share/sticker-library',
            entries: [{ path: '作品/原图.png', size: 1024 }], missing: [], bytes: 1024,
          },
        }
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()

    await wrapper.get('[data-test="export-target"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="preview-summary"]').exists()).toBe(true)

    await wrapper.get('[data-test="mode-migration"]').setValue()
    expect(wrapper.find('[data-test="preview-summary"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="execute-export"]').element.disabled).toBe(true)

    await wrapper.get('[data-test="preview-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="preview-summary"]').exists()).toBe(true)
    await wrapper.get('[data-test="cleanup"]').setValue(true)
    expect(wrapper.find('[data-test="preview-summary"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="execute-export"]').element.disabled).toBe(true)
    expect(send).toHaveBeenCalledTimes(3) // 初始状态、两次预览
  })

  it('部分传输结果使用警示样式并保留可继续执行的提示', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_preview') {
        return { status: 'ok', data: {
          plan_id: 'plan-partial', mode: 'backup', target: '/Volumes/share/sticker-library',
          entries: [{ path: '作品/原图.png', size: 1024 }], missing: [], bytes: 1024,
        } }
      }
      if (cmd === 'library_execute') {
        return { status: 'ok', data: {
          state: 'cleanup_partial', copied: ['作品/原图.png'], cleaned: [], missing: [], errors: [],
        } }
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    await wrapper.get('[data-test="export-target"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="preview-export"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="execute-export"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="execution-result"]').classes()).toContain('transfer-warning')
    expect(wrapper.get('[data-test="transfer-tip"]').classes()).toContain('transfer-warning')
    expect(wrapper.get('[data-test="transfer-tip"]').text()).not.toContain('✓')
    expect(wrapper.text()).toContain('仍可继续')
  })

  it('复制导入按实际 copied 数量展示结果，而不是渲染结果对象', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_import') {
        return { status: 'ok', data: {
          ...status(),
          imported: { state: 'completed', copied: ['作品/一.png', '作品/二.png'], cleaned: [] },
        } }
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    await wrapper.get('[data-test="choose-library"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="import-library"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="transfer-tip"]').text()).toContain('已导入 2 项')
    expect(wrapper.get('[data-test="transfer-tip"]').text()).not.toContain('[object Object]')
  })

  it('需要明确确认旧作品关联后才绑定账号，并展示 API 错误', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_bind_account') {
        return { status: 'error', errors: [{ message: '当前登录账号与绑定账号不一致' }] }
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    expect(wrapper.text()).toContain('平台登录账号')
    expect(wrapper.text()).toContain('与发布设置中的登录账号保持一致')
    const bind = wrapper.get('[data-test="bind-account"]')
    expect(bind.element.disabled).toBe(true)
    await wrapper.get('[data-test="account-id"]').setValue('wx-account-1')
    await wrapper.get('[data-test="legacy-confirm"]').setValue(true)
    expect(bind.element.disabled).toBe(false)
    await bind.trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_bind_account', {
      account: 'wx-account-1', confirm_legacy: true,
    })
    expect(wrapper.text()).toContain('当前登录账号与绑定账号不一致')
  })

  it('展示资源库离线、警告和设置冲突状态，不把离线误当成空库', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status({
        offline: true,
        connected: false,
        warnings: ['资源库目录暂时不可用'],
        settings_conflicts: [{ setting_type: 'prefs', message: '另一台电脑有更新的生图设置' }],
      }) }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()

    expect(wrapper.text()).toContain('共享库离线')
    expect(wrapper.text()).toContain('资源库目录暂时不可用')
    expect(wrapper.text()).toContain('设置版本冲突')
    expect(wrapper.text()).toContain('另一台电脑有更新的生图设置')
    expect(wrapper.get('[data-test="library-root"]').text()).toContain('未连接')
    expect(send).toHaveBeenCalledWith('library_status', {})
  })

  it('连接共享库与复制导入使用不同命令，取消选目录不会发请求', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      return { status: 'ok', data: status({ connected: true, root: '/Volumes/share' }) }
    })
    window.api.selectDirectory.mockResolvedValueOnce(null)
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    await wrapper.get('[data-test="choose-library"]').trigger('click')
    await flushPromises()
    expect(send).not.toHaveBeenCalledWith('library_connect', expect.anything())
    window.api.selectDirectory.mockResolvedValueOnce('/Volumes/share')
    await wrapper.get('[data-test="choose-library"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="connect-library"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_connect', { path: '/Volumes/share' })
    await wrapper.get('[data-test="import-library"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_import', { path: '/Volumes/share' })
  })

  it('刷新按钮使用库刷新命令而不是把失联误当成空库', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status() }
      if (cmd === 'library_refresh') return {
        status: 'ok', data: status({
          connected: true, root: '/Volumes/share', workspace_path: '/Volumes/.sticker-maker-workspaces/device/library/account/episodes',
        }),
      }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    send.mockClear()
    await wrapper.get('[data-test="refresh-library"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_refresh', {})
    expect(wrapper.get('[data-test="library-root"]').text()).toContain('/Volumes/share')
    expect(wrapper.get('[data-test="workspace-path"]').text()).toContain('.sticker-maker-workspaces')
    expect(wrapper.text()).toContain('Syncthing 只需同步资源库目录，旁边的工作缓存无需同步')
  })

  it('提交结果待核对必须由用户确认，不自动重试', async () => {
    const send = apiFor((cmd) => {
      if (cmd === 'library_status') return { status: 'ok', data: status({
        unresolved_operations: [{ operation_id: 'op-1', work_id: 'work-1', album_name: '一弹', phase: '提交超时' }],
      }) }
      if (cmd === 'library_reconcile') return { status: 'ok', data: {} }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(ResourceLibraryPanel)
    await flushPromises()
    expect(wrapper.text()).toContain('提交结果待核对')
    await wrapper.get('[data-test="reconcile-submitted-op-1"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('library_reconcile', {
      operation_id: 'op-1', outcome: 'submitted',
    })
    expect(send).not.toHaveBeenCalledWith('publish_episode', expect.anything())
  })
})

describe('作品资源状态与编辑权限', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('占位符可以打开详情，但没有本机路径时仍调用 work_id 查询', async () => {
    const send = apiFor((cmd, args) => {
      if (cmd === 'list_episodes') {
        return { status: 'ok', data: { episodes: [{
          name: '平台占位符', path: '', work_id: 'work-1', account_id: 'acct-1',
          resource_state: 'placeholder', can_edit: false, can_publish: true,
          published: true, complete: false, platform_status: '已上架', sticker_count: 0,
        }] } }
      }
      if (cmd === 'list_series') return { status: 'ok', data: { series: [] } }
      if (cmd === 'get_episode') return { status: 'ok', data: {
        name: '平台占位符', path: '', work_id: 'work-1', account_id: 'acct-1',
        resource_state: 'placeholder', can_edit: false, can_publish: true,
        meta: { album_name: '平台占位符', published: true }, stickers: [], characters: [],
      } }
      return { status: 'ok', data: {} }
    })
    const wrapper = mount(EpisodesPanel)
    await flushPromises()
    expect(wrapper.text()).toContain('资源未到齐')
    await wrapper.get('[data-test="episode-detail"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('get_episode', { work_id: 'work-1', episode_dir: '' })
  })

  it('占位符优先于过期权限标记，修改和上传处理器均不发请求', async () => {
    const send = apiFor(() => ({ status: 'ok', data: { success: true } }))
    const store = useEngineStore()
    store.selectedEpisode = {
      path: '/tmp/placeholder', work_id: 'work-1', account_id: 'acct-1',
      resource_state: 'placeholder', can_edit: false, can_publish: true,
      meta: { album_name: '平台作品', published: true, intro: '' },
      stickers: [], characters: [],
    }
    const wrapper = mount(EpisodeDetailPanel)
    await flushPromises()
    expect(wrapper.get('[data-test="edit-blocked"]').exists()).toBe(true)
    send.mockClear()
    await wrapper.get('[data-test="save-name"]').trigger('click')
    await wrapper.get('[data-test="publish"]').trigger('click')
    await flushPromises()
    expect(send).not.toHaveBeenCalledWith('publish_episode', expect.anything())
    expect(send).not.toHaveBeenCalledWith('update_episode_meta', expect.anything())
  })

  it.each(['conflict', 'pending', 'offline'])('%s 状态优先于过期权限标记，并提供直达资源库入口', async (resourceState) => {
    const send = apiFor(() => ({ status: 'ok', data: {} }))
    const store = useEngineStore()
    store.selectedEpisode = {
      path: '/tmp/conflict', work_id: 'work-conflict', account_id: 'acct-1',
      resource_state: resourceState, can_edit: true, can_publish: true,
      meta: { album_name: '冲突作品', published: true, intro: '' }, stickers: [], characters: [],
    }
    const wrapper = mount(EpisodeDetailPanel)
    await flushPromises()
    expect(wrapper.get('[data-test="save-name"]').element.disabled).toBe(true)
    expect(wrapper.get('[data-test="publish"]').element.disabled).toBe(true)
    send.mockClear()
    await wrapper.get('[data-test="save-name"]').trigger('click')
    await wrapper.get('[data-test="publish"]').trigger('click')
    expect(send).not.toHaveBeenCalledWith('update_episode_meta', expect.anything())
    expect(send).not.toHaveBeenCalledWith('publish_episode', expect.anything())

    await wrapper.get('[data-test="resource-library-link"]').trigger('click')
    expect(store.phase).toBe('settings')
    expect(store.settingsTab).toBe('resource')
  })

  it('设置页把资源库作为独立 tab，与发布账号面板互斥', async () => {
    apiFor(() => ({ status: 'ok', data: {} }))
    const wrapper = mount(SettingsPanel, {
      global: {
        stubs: {
          WizardStepBase: true, WizardStepMode: true, WizardStepChar: true, WizardStepPref: true,
          ResourceLibraryPanel: { template: '<div data-test="resource-library-stub">资源库</div>' },
        },
      },
    })
    expect(wrapper.text()).toContain('保存生图设置')
    await wrapper.get('[data-test="resource-tab"]').trigger('click')
    expect(wrapper.get('[data-test="resource-library-stub"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('微信表情开放平台账号')
  })
})
