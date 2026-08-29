import { describe, it, expect } from 'vitest'
import { parseReasonItems, reasonCount } from '../../src/renderer/utils/reason'

// 2026-08-29 抓取的 61 真实驳回理由（3 条：名称空格 + 图标两条）
const REASON_61 = `表情名称
周三涵做表情 61
表情名称应避免出现空格，需要修改。
聊天页图标
请使用只含有形象头部的正面图像做图标。
聊天页图标在手机上展示位置较小，请去除不必要的文字信息和装饰图案。`

describe('驳回理由解析（多条理由完整展示）', () => {
  it('61 的三条理由全部解析出来，专辑名行被过滤', () => {
    const items = parseReasonItems(REASON_61, '周三涵做表情 61')
    // 组：表情名称（1条）+ 聊天页图标（2条合并）
    expect(items).toHaveLength(2)
    expect(items[0].group).toBe('表情名称')
    expect(items[0].text).toContain('避免出现空格')
    expect(items[1].group).toBe('聊天页图标')
    expect(items[1].text).toContain('只含有形象头部')
    expect(items[1].text).toContain('展示位置较小')
    // 专辑名行不混入任何条目
    expect(JSON.stringify(items)).not.toContain('周三涵做表情 61')
  })

  it('条数按文本段计（61 = 3 条）', () => {
    expect(reasonCount(REASON_61, '周三涵做表情 61')).toBe(3)
  })

  it('标题行「表情驳回理由」不混入', () => {
    const items = parseReasonItems('表情驳回理由\n聊天页图标\n图标过小。', '')
    expect(items).toHaveLength(1)
    expect(items[0].group).toBe('聊天页图标')
  })

  it('长句组名误判防护：以句号收尾的长文本不当组名', () => {
    const items = parseReasonItems('总体驳回理由\n表情图中含有多余边框线，显示效果不佳，需要去除。', '')
    expect(items).toHaveLength(1)
    expect(items[0].group).toBe('总体驳回理由')
    expect(items[0].text).toContain('多余边框线')
  })

  it('无组名的裸文本也能出条目', () => {
    const items = parseReasonItems('直接一句理由。', '')
    expect(items).toEqual([{ group: '', text: '直接一句理由。' }])
  })

  it('空/undefined 安全', () => {
    expect(parseReasonItems('', '')).toEqual([])
    expect(parseReasonItems(undefined, undefined)).toEqual([])
    expect(reasonCount('', '')).toBe(0)
  })
})
