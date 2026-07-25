import { describe, expect, it } from 'vitest'
import { isNewerVersion, validateDownloadUrl } from '../src/main/updater'

describe('desktop updater safety', () => {
  it('compares semantic version segments instead of raw strings', () => {
    expect(isNewerVersion('0.2.0', '0.1.9')).toBe(true)
    expect(isNewerVersion('0.10.0', '0.9.9')).toBe(true)
    expect(isNewerVersion('0.1.0', '0.1.0')).toBe(false)
    expect(isNewerVersion('0.1.0', '0.2.0')).toBe(false)
  })

  it('accepts only https update downloads', () => {
    expect(validateDownloadUrl('https://example.com/app.zip')).toBe(true)
    expect(validateDownloadUrl('http://example.com/app.zip')).toBe(false)
    expect(validateDownloadUrl('file:///tmp/app.zip')).toBe(false)
    expect(validateDownloadUrl('not a url')).toBe(false)
  })
})
