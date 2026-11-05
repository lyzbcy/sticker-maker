// One subscription owner per Pinia store. All callbacks share its disposal gate.
// Business commands stay in engine.js: events never submit, retry or reconcile work.
export function bindEngineEvents(api, state) {
  let disposed = false
  const subscriptions = []
  const listen = (method, callback) => {
    if (typeof api?.[method] !== 'function') return
    const off = api[method]((...args) => { if (!disposed) callback(...args) })
    if (typeof off === 'function') subscriptions.push(off)
  }
  const resetBusy = () => {
    state.running.value = false
    state.publishing.value = false
    state.installing.value = false
    state.progress.value = null
    state.publishProgress.value = null
    state.runStartedAt.value = null
    state.activeTasks.value = {}
    state.activityIsHistorical.value = true
  }
  listen('onTask', task => {
    if (!task || task.id == null) return
    if (task.state === 'end') {
      delete state.activeTasks.value[task.id]
      state.activityIsHistorical.value = true
    } else {
      state.activeTasks.value[task.id] = { ...state.activeTasks.value[task.id], ...task }
    }
  })
  listen('onProgress', ev => {
    if (!ev) return
    state.pushActivity({ stage: ev.stage, message: ev.message }, false)
    if (ev.stage === 'install' && state.installing.value) state.installLog.value.push(ev.message)
    else if (state.publishing.value) state.publishProgress.value = ev
    else if (state.running.value) state.progress.value = ev
  })
  listen('onRestarting', () => {
    resetBusy()
    const message = '引擎意外退出，正在自动重启…请稍后重试'
    state.pushActivity({ stage: 'SYS', message })
    state.lastError.value = [{ message }]
  })
  listen('onExit', data => {
    resetBusy()
    if (data?.code === 3) {
      state.lastError.value = [{ message: '检测到另一个「表情包一键制作」正在运行。为避免多实例并发造成版本冲突，本窗口的引擎已停止——请关闭其他窗口后重启本应用。' }]
      state.pushActivity({ stage: 'SYS', message: '引擎被其他实例占用（单实例锁），已停止' })
    } else if (data?.code !== 0) {
      const message = '制作引擎已退出，请检查问题与警告后重试；已有作品和提交记录保持不变'
      state.lastError.value = [{ message }]
      state.pushActivity({ stage: 'SYS', message })
    }
  })
  // Keep the existing updater messages; no updater decisions or requests live here.
  listen('onUpdateProgress', ev => {
    if (!ev) return
    if (ev.stage === 'checking') state.pushActivity({ stage: '更新', message: '正在重新检查最新版本…' })
    else if (ev.stage === 'download') state.pushActivity({ stage: '更新', message: `正在下载${ev.version ? ' ' + ev.version : '新版本'}… ${ev.percent}%（${ev.receivedMB}/${ev.totalMB} MB）` })
    else if (ev.stage === 'verify') state.pushActivity({ stage: '更新', message: `下载完成，正在校验${ev.version ? ' ' + ev.version : ''}安装包…` })
  })
  return () => {
    if (disposed) return
    disposed = true
    for (const unsubscribe of subscriptions.splice(0)) unsubscribe()
  }
}
