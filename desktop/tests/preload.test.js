import { createRequire } from 'node:module'
import { describe, expect, it } from 'vitest'

const require = createRequire(import.meta.url)
const { toFileUrl } = require('../src/preload/index.js')

describe('preload 文件地址转换', () => {
  it('正确编码中文、空格和 URL 特殊字符', () => {
    expect(toFileUrl('/Users/星 星/base#1?.png')).toBe(
      'file:///Users/%E6%98%9F%20%E6%98%9F/base%231%3F.png',
    )
  })

  it('保留已经转换的 file URL，并处理空值', () => {
    expect(toFileUrl('file:///tmp/base.png')).toBe('file:///tmp/base.png')
    expect(toFileUrl('')).toBe('')
  })
})
