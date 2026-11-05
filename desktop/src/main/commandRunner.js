// One lifecycle per actual bridge request; polling stays silent unless it emits progress.
const labels = { run:'制作表情', run_batch:'批量制作', publish_episode:'投稿', sync_platform_status:'同步状态', sync_sticker_metrics:'读取单图发送报告', shelf_passed:'一键上架', install_codex:'安装生图组件', install_chromium:'安装浏览器', list_episodes:'读取作品', project_location_inspect:'识别资源位置', project_location_connect:'连接资源', save_prefs:'保存设置' }

function createCommandRunner({ bridge, emit, log, flattenError, now = Date.now }) {
  let sequence = 0
  return async function runCommand(cmd, args) {
    const task = { id:String(++sequence), command:cmd, startedAt:now(), message:labels[cmd] || '处理资源任务' }
    let announced = false
    let settled = false
    const notify = data => emit('task-status', { ...task, ...data })
    const start = () => { if (!announced) { announced = true; notify({ state:'start' }) } }
    if (labels[cmd] || /^(project_|library_)(?!status)/.test(cmd)) start()
    try {
      const result = await bridge.send(cmd, args, ev => {
        if (settled) return
        start()
        emit('python-progress', ev)
        notify({ state:'progress', message:ev.message, stage:ev.stage, percent:ev.percent })
      })
      log({ stage:'command', message:`${cmd} ${result.status || '完成'}，耗时 ${((now()-task.startedAt)/1000).toFixed(1)} 秒` })
      return result
    } catch (err) {
      return flattenError(err)
    } finally {
      settled = true
      if (announced) notify({ state:'end' })
    }
  }
}
module.exports = { createCommandRunner }
