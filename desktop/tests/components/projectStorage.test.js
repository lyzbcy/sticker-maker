import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProjectStoragePanel from '../../src/renderer/components/ProjectStoragePanel.vue'
import ProjectSlimPanel from '../../src/renderer/components/ProjectSlimPanel.vue'

beforeEach(() => {
  window.api = {
    selectDirectory: vi.fn(async () => 'D:/表情工程'),
    onProgress: vi.fn(),
    send: vi.fn(async cmd => {
      if (cmd === 'project_slim_preview') return { status: 'ok', data: { plan_id: 'slim', bytes: 1024, delete_sources: true } }
      return { status: 'ok', data: {} }
    }),
  }
})

describe('规范工程转换', () => {
  it('取消连接目录选择不会沿用先前的目标执行连接', async () => {
    const w = mount(ProjectStoragePanel)
    await w.get('[data-test=project-target]').trigger('click'); await flushPromises()
    window.api.selectDirectory.mockResolvedValue(null)
    await w.get('[data-test=project-connect]').trigger('click'); await flushPromises()
    expect(window.api.send).not.toHaveBeenCalledWith('project_connect', expect.anything())
  })
  it('先预览，缺失时阻止转换，并显示错误项', async () => {
    window.api.send.mockResolvedValue({ status: 'ok', data: { plan_id: 'convert', entries: [{}], missing: [{ reason: '本机评分分歧' }] } })
    const w = mount(ProjectStoragePanel)
    await w.get('[data-test=project-target]').trigger('click'); await flushPromises()
    await w.get('[data-test=project-preview]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('本机评分分歧')
    expect(w.get('[data-test=project-execute]').element.disabled).toBe(true)
    expect(window.api.send).not.toHaveBeenCalledWith('project_migration_execute', expect.anything())
  })

  it('旧副本清理先展示净收益，确认多端切换后才允许执行', async () => {
    window.api.send.mockResolvedValue({ status: 'ok', data: { plan_id: 'cleanup', estimated_freed_bytes: 1024, history_bytes: 16 } })
    const w = mount(ProjectStoragePanel, { props: { direct: true, migrationId: 'migration' } })
    await w.get('[data-test=old-copies-preview]').trigger('click'); await flushPromises()
    expect(w.get('[data-test=old-copies-execute]').element.disabled).toBe(true)
    await w.get('[data-test=old-copies-confirm]').setValue(true)
    expect(w.get('[data-test=old-copies-execute]').element.disabled).toBe(false)
    await w.get('[data-test=old-copies-execute]').trigger('click'); await flushPromises()
    expect(window.api.send).toHaveBeenCalledWith('project_old_copies_execute', { plan_id: 'cleanup' })
  })
})

describe('工程瘦身', () => {
  it('删除原图默认关闭，预览后需确认才能删除', async () => {
    const w = mount(ProjectSlimPanel, { props: { path: 'D:/表情工程/周三涵做表情37', mode: 'full', canEdit: true } })
    expect(w.get('[data-test=delete-sources]').element.checked).toBe(false)
    await w.get('[data-test=delete-sources]').setValue(true)
    await w.get('[data-test=slim-preview]').trigger('click'); await flushPromises()
    expect(w.get('[data-test=slim-execute]').element.disabled).toBe(true)
    await w.get('[data-test=confirm-source-removal]').setValue(true)
    await w.get('[data-test=slim-execute]').trigger('click'); await flushPromises()
    expect(window.api.send).toHaveBeenCalledWith('project_slim_execute', { plan_id: 'slim', confirm_discard_sources: true })
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('切换删除范围使原预览失效', async () => {
    const w = mount(ProjectSlimPanel, { props: { path: 'D:/project', mode: 'full', canEdit: true } })
    await w.get('[data-test=slim-preview]').trigger('click'); await flushPromises()
    expect(w.find('[data-test=slim-execute]').exists()).toBe(true)
    await w.get('[data-test=delete-sources]').setValue(true)
    expect(w.find('[data-test=slim-execute]').exists()).toBe(false)
  })

  it('精简工程提示能力限制，不再提供重复删除原图入口', () => {
    const w = mount(ProjectSlimPanel, { props: { path: 'D:/project', mode: 'delivery', canEdit: true } })
    expect(w.text()).toContain('重新裁切、加字和生成素材需导入完整工程')
    expect(w.find('[data-test=delete-sources]').exists()).toBe(false)
  })
})
