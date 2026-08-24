const path = require('path')
const { resolvePackagedCliPath, resolveDevPython } = require('../src/main/pythonBridge')
const { pickUpdateAsset } = require('../src/main/updater')

describe('resolvePackagedCliPath（平台二进制名）', () => {
  const isWin = process.platform === 'win32'

  test('win32 下带 .exe 后缀', () => {
    const p = resolvePackagedCliPath('/r', 'win32')
    expect(p).toBe(path.join('/r', 'sticker-engine-cli', 'sticker-engine-cli.exe'))
  })

  test('darwin 下无后缀', () => {
    const p = resolvePackagedCliPath('/r', 'darwin')
    expect(p).toBe(path.join('/r', 'sticker-engine-cli', 'sticker-engine-cli'))
  })

  test('默认用当前平台', () => {
    const p = resolvePackagedCliPath('/r')
    expect(p.endsWith('.exe')).toBe(isWin)
  })
})

describe('resolveDevPython（dev 模式 venv 路径）', () => {
  beforeEach(() => { delete process.env.STICKER_ENGINE_PYTHON })
  afterEach(() => { delete process.env.STICKER_ENGINE_PYTHON })

  test('按平台选择 venv 布局', () => {
    expect(resolveDevPython('/repo', 'win32')).toBe(path.join('/repo', 'sticker_engine', '.venv', 'Scripts', 'python.exe'))
    expect(resolveDevPython('/repo', 'darwin')).toBe(path.join('/repo', 'sticker_engine', '.venv', 'bin', 'python'))
  })

  test('环境变量覆盖优先', () => {
    process.env.STICKER_ENGINE_PYTHON = '/custom/python'
    expect(resolveDevPython('/repo', 'win32')).toBe('/custom/python')
  })
})

describe('pickUpdateAsset（双平台更新资产选择）', () => {
  const dual = {
    version: '0.3.0',
    downloadUrl: 'https://example.com/mac.zip',
    sha256: 'aaa',
    platforms: {
      mac: { url: 'https://example.com/mac.zip', sha256: 'aaa' },
      win: { url: 'https://example.com/win.exe', sha256: 'bbb' },
    },
  }

  test('新 schema：win32 选 win 资产', () => {
    expect(pickUpdateAsset(dual, 'win32')).toEqual({ url: 'https://example.com/win.exe', sha256: 'bbb' })
  })

  test('新 schema：darwin 选 mac 资产', () => {
    expect(pickUpdateAsset(dual, 'darwin')).toEqual({ url: 'https://example.com/mac.zip', sha256: 'aaa' })
  })

  test('旧 schema（无 platforms）：mac 回退顶层 downloadUrl', () => {
    const legacy = { version: '0.2.1', downloadUrl: 'https://example.com/mac.zip', sha256: 'aaa' }
    expect(pickUpdateAsset(legacy, 'darwin')).toEqual({ url: 'https://example.com/mac.zip', sha256: 'aaa' })
  })

  test('旧 schema 下 win32 无资产（老 manifest 没发过 win 包）', () => {
    const legacy = { version: '0.2.1', downloadUrl: 'https://example.com/mac.zip' }
    expect(pickUpdateAsset(legacy, 'win32')).toBeNull()
  })

  test('manifest 为空时返回 null', () => {
    expect(pickUpdateAsset(null, 'win32')).toBeNull()
    expect(pickUpdateAsset({}, 'darwin')).toBeNull()
  })
})
