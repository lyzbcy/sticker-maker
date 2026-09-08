const { PythonBridge } = require('../src/main/pythonBridge')

describe('PythonBridge (mock child_process)', () => {
  let bridge, fakeProc, lastReqId

  beforeEach(() => {
    fakeProc = {
      stdout: { setEncoding: () => {}, on: () => {} },
      stderr: { on: () => {} },
      stdin: { write: (data) => { lastReqId = JSON.parse(data).id } },
      on: () => {},
      kill: () => {},
    }
    bridge = new PythonBridge('dev')
    bridge.proc = fakeProc
    lastReqId = null
  })

  test('send 返回 promise，收到 ok result 时 resolve', async () => {
    const p = bridge.send('get_version')
    bridge._onData(JSON.stringify({ id: lastReqId, type: 'result', status: 'ok', data: { version: '0.1.0' } }) + '\n')
    const result = await p
    expect(result.status).toBe('ok')
    expect(result.data.version).toBe('0.1.0')
  })

  test('progress 事件触发 progressCb', async () => {
    const progressSeen = []
    const p = bridge.send('run', {}, (ev) => progressSeen.push(ev))
    bridge._onData(JSON.stringify({ id: lastReqId, type: 'progress', stage: 'S1', percent: 0.5 }) + '\n')
    bridge._onData(JSON.stringify({ id: lastReqId, type: 'result', status: 'ok', data: {} }) + '\n')
    await p
    expect(progressSeen.length).toBe(1)
    expect(progressSeen[0].percent).toBe(0.5)
  })

  test('fail result 导致 promise reject', async () => {
    const p = bridge.send('check_codex')
    bridge._onData(JSON.stringify({ id: lastReqId, type: 'result', status: 'fail', errors: [] }) + '\n')
    await expect(p).rejects.toMatchObject({ status: 'fail' })
  })

  test('多行缓冲正确切分（一条 data 含两个事件）', async () => {
    const resolved = []
    const p1 = bridge.send('x').then(() => resolved.push(1)).catch(() => {})
    const id1 = lastReqId
    const p2 = bridge.send('y').then(() => resolved.push(1)).catch(() => {})
    const id2 = lastReqId
    bridge._onData(JSON.stringify({ id: id1, type: 'result', status: 'ok' }) + '\n' +
                   JSON.stringify({ id: id2, type: 'result', status: 'ok' }) + '\n')
    await Promise.all([p1, p2])
    expect(resolved.length).toBe(2)
  })

  test('未启动时 send 立即 reject', async () => {
    bridge.proc = null
    await expect(bridge.send('x')).rejects.toThrow('CLI 未启动')
  })

  test('stop 贯通平台命令：sync/shelf 在跑时可取消（无 run 时不再拒绝）', async () => {
    // sync 平台命令在跑
    const p = bridge.send('sync_platform_status')
    expect(bridge.cancelableIds.size).toBe(1)
    const syncId = [...bridge.cancelableIds][0]
    // 用户点取消 → stop 命令带上真实 reqId
    const stopP = bridge.stop()
    const stopId = lastReqId
    bridge._onData(JSON.stringify({ id: stopId, type: 'result', status: 'ok' }) + '\n')
    await stopP
    // 平台命令收到取消结果（ok + cancelled）
    bridge._onData(JSON.stringify({ id: syncId, type: 'result', status: 'ok', data: { cancelled: true } }) + '\n')
    const res = await p
    expect(res.data.cancelled).toBe(true)
    expect(bridge.cancelableIds.size).toBe(0)   // 结果回来后清理
  })

  test('stop 无可取消任务时仍 reject（缺省 target 且无 run 无平台命令）', async () => {
    await expect(bridge.stop()).rejects.toThrow('无正在运行的任务')
  })
})
