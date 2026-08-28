import { defineStore } from 'pinia'
import { ref } from 'vue'

const nearOne = (value) => Math.abs(value - 1) <= 0.001
const sumValues = (object) => Object.values(object || {}).reduce(
  (total, value) => total + (Number(value) || 0), 0,
)

export function validatePrefs(prefs, characters = {}) {
  const modeSum = sumValues(prefs?.mode_probs)
  if (!nearOne(modeSum)) {
    return {
      ok: false,
      message: `模式概率总和必须为 100%，当前 ${Math.round(modeSum * 100)}%`,
    }
  }
  const names = Object.keys(characters)
  if (names.length === 0) {
    return { ok: false, message: '至少需要一个带 base 图的角色' }
  }
  const charSum = names.reduce(
    (total, name) => total + (Number(prefs?.single_char_probs?.[name]) || 0), 0,
  )
  if (!nearOne(charSum)) {
    return {
      ok: false,
      message: `角色概率总和必须为 100%，当前 ${Math.round(charSum * 100)}%`,
    }
  }
  for (const name of names) {
    const baseKeys = Object.keys(characters[name]?.bases || {})
    if (baseKeys.length === 0) {
      return { ok: false, message: `角色「${name}」至少需要一张 base 图` }
    }
    const baseSum = baseKeys.reduce(
      (total, key) => total + (Number(prefs?.base_probs?.[name]?.[key]) || 0), 0,
    )
    if (!nearOne(baseSum)) {
      return {
        ok: false,
        message: `角色「${name}」的 base 概率总和必须为 100%，当前 ${Math.round(baseSum * 100)}%`,
      }
    }
  }
  return { ok: true, message: '' }
}

export const useEngineStore = defineStore('engine', () => {
  const phase = ref('launch')   // launch | wizard | main | settings | tools
  const firstRun = ref(true)
  const prefs = ref(null)
  const codexStatus = ref(null)
  const characters = ref({})
  const episodes = ref([])
  // run 状态
  const running = ref(false)
  const progress = ref(null)
  const lastEpisode = ref(null)
  const lastError = ref(null)
  const runStartedAt = ref(null)     // 本次 run 开始时间戳（ms），底边栏显示已用时
  // 活动日志：所有 progress 事件的滚动记录（底边栏展示"在做什么/在等什么"）
  const activity = ref([])
  const ACTIVITY_CAP = 60
  // codex 安装状态
  const installing = ref(false)
  const installLog = ref([])
  // 发布 / Agent / 内存日志
  const publishing = ref(false)
  const publishProgress = ref(null)
  const publishResult = ref(null)
  const logs = ref([])
  const agentStatus = ref({ running: false, host: '127.0.0.1', port: null, token: null })
  const agentPrompt = ref('')
  // 作品库 / 详情
  const seriesList = ref([])
  const selectedEpisode = ref(null)   // get_episode 返回的详情

  // 确保 window.api 存在（开发模式 Electron 注入）
  // 关键：contextIsolation 下渲染进程 → preload 的参数会先经过 contextBridge
  // 的跨世界 structured clone，Vue 响应式 Proxy 在这一步就被拒
  // （"An object could not be cloned."）。必须在渲染进程侧先深拷贝剥掉 Proxy，
  // preload 里的兜底拷贝来不及执行。
  const rawApi = typeof window !== 'undefined' && window.api ? window.api : null
  const api = rawApi ? {
    ...rawApi,
    send: (cmd, args) => rawApi.send(cmd, JSON.parse(JSON.stringify(args ?? {}))),
  } : null

  async function init() {
    if (!api) { phase.value = 'wizard'; return }
    // 超时兜底：cli 冷启动可能慢，但 15 秒还没响应就降级进向导
    const timeout = new Promise(resolve => setTimeout(() => resolve({__timeout: true}), 15000))
    try {
      const res = await Promise.race([api.send('load_prefs'), timeout])
      if (res && res.__timeout) {
        // 超时：引擎可能还在启动，先进向导（用户可重试）
        lastError.value = [{ message: '引擎启动较慢，已进入向导。如 codex 检测失败请点重新检测。' }]
        prefs.value = defaultPrefs()
        phase.value = 'wizard'
        return
      }
      if (res && res.status === 'ok') {
        prefs.value = res.data.prefs || defaultPrefs()
        if (prefs.value.default_series_id === undefined) prefs.value.default_series_id = null
        firstRun.value = res.data.first_run
        phase.value = firstRun.value ? 'wizard' : 'main'
      } else {
        prefs.value = defaultPrefs()
        phase.value = 'wizard'
      }
    } catch (e) {
      prefs.value = defaultPrefs()
      phase.value = 'wizard'
    }
  }

  function defaultPrefs() {
    return {
      mode_probs: { single: 1, duo: 0, trio: 0, quad: 0 },
      single_char_probs: { 星星布丁: 0.7, 捞鱼: 0.3 },
      base_probs: {},
      grid_size: 4,
      transparent_default: true,
      ref_lib_priority: true,
      story_mode: true,
      default_series_id: null,   // 默认系列：run 成功后自动编号命名（null=不自动）
    }
  }

  async function checkCodex() {
    if (!api) return
    try {
      const res = await api.send('check_codex')
      codexStatus.value = (res && res.data) || { image_ready: false }
    } catch (e) {
      codexStatus.value = (e && e.data) || { image_ready: false, guidance_msg: '检测失败' }
    }
  }

  async function installCodex() {
    if (!api) return
    installing.value = true
    installLog.value = []
    lastError.value = null
    try {
      const res = await api.send('install_codex')
      if (res && res.status === 'ok') {
        // 安装成功，重新检测
        await checkCodex()
      } else {
        lastError.value = (res && res.errors) || [{ message: '安装失败' }]
        if (res && res.data && res.data.hint) lastError.value.push({ message: res.data.hint })
      }
    } catch (e) {
      lastError.value = [{ message: (e && (e.message || (e.errors && e.errors[0] && e.errors[0].message))) || '安装失败' }]
      if (e && e.data && e.data.hint) lastError.value.push({ message: e.data.hint })
    } finally {
      installing.value = false
    }
  }

  async function loadCharacters() {
    if (!api) return
    const res = await api.send('list_characters')
    if (res && res.status === 'ok') {
      characters.value = res.data.characters || {}
      ensureProbabilityDefaults()
    }
  }

  function ensureProbabilityDefaults() {
    if (!prefs.value) prefs.value = defaultPrefs()
    if (!prefs.value.single_char_probs) prefs.value.single_char_probs = {}
    if (!prefs.value.base_probs) prefs.value.base_probs = {}
    const names = Object.keys(characters.value)
    const currentCharTotal = names.reduce(
      (total, name) => total + (Number(prefs.value.single_char_probs[name]) || 0), 0,
    )
    if (currentCharTotal <= 0 && names.length) {
      const equal = 1 / names.length
      names.forEach(name => { prefs.value.single_char_probs[name] = equal })
    } else {
      names.forEach(name => {
        if (prefs.value.single_char_probs[name] == null) {
          prefs.value.single_char_probs[name] = 0
        }
      })
    }
    names.forEach(name => {
      const info = characters.value[name] || {}
      const keys = Object.keys(info.bases || {})
      const saved = prefs.value.base_probs[name] || {}
      const backend = info.base_probs || {}
      const candidate = {}
      keys.forEach(key => {
        candidate[key] = Number(saved[key] ?? backend[key] ?? 0)
      })
      const total = sumValues(candidate)
      if (total <= 0 && keys.length) {
        keys.forEach(key => { candidate[key] = 1 / keys.length })
      } else if (total > 0) {
        keys.forEach(key => { candidate[key] /= total })
      }
      prefs.value.base_probs[name] = candidate
    })
  }

  async function savePrefs(newPrefs) {
    const validation = validatePrefs(newPrefs, characters.value)
    if (!validation.ok) {
      lastError.value = [{ message: validation.message }]
      return false
    }
    if (!api) { phase.value = 'main'; return true }
    try {
      // prefs 是 Vue 响应式 Proxy，无法被 Electron IPC structured clone 序列化，
      // 必须先深拷贝成纯对象，否则 invoke 抛 "An object could not be cloned."
      const plainPrefs = JSON.parse(JSON.stringify(newPrefs))
      const res = await api.send('save_prefs', { prefs: plainPrefs })
      if (res && res.status === 'ok') {
        prefs.value = plainPrefs
        firstRun.value = false
        phase.value = 'main'
        lastError.value = null
        return true
      }
      lastError.value = [{ message: '保存失败' }]
      return false
    } catch (e) {
      lastError.value = [{ message: (e && e.message) || '保存失败' }]
      return false
    }
  }

  // I4 修复：清结果回到待机态
  function clearResult() {
    lastEpisode.value = null
    lastError.value = null
  }

  // 底边栏活动日志：滚动保留最近 ACTIVITY_CAP 条
  function pushActivity(entry) {
    activity.value.push({ t: Date.now(), stage: '', message: '', ...entry })
    if (activity.value.length > ACTIVITY_CAP) {
      activity.value.splice(0, activity.value.length - ACTIVITY_CAP)
    }
  }

  async function runGenerate() {
    if (!api) return
    running.value = true
    progress.value = null
    lastError.value = null
    lastEpisode.value = null
    runStartedAt.value = Date.now()
    pushActivity({ stage: 'RUN', message: '开始生图任务' })
    try {
      const res = await api.send('run')
      if (res && res.status === 'ok') {
        lastEpisode.value = res.data
        pushActivity({ stage: 'RUN', message: `任务完成：${res.data?.stickers ?? 0} 张表情` })
      } else {
        lastError.value = (res && res.errors) || [{ message: (res && res.aborted_reason) || '运行失败' }]
      }
    } catch (e) {
      lastError.value = (e && e.errors) || [{ message: (e && e.message) || '运行失败' }]
    } finally {
      running.value = false
      progress.value = null
      runStartedAt.value = null
    }
  }

  async function stopRun() {
    if (!api) return
    await api.stop('all').catch(() => {})
  }

  async function loadEpisodes() {
    if (!api) return
    const res = await api.send('list_episodes')
    if (res && res.status === 'ok') episodes.value = res.data.episodes || []
    maybeAskForReview()
  }

  // ---- 求好评（prompt「不打扰用户的求好评」）----
  // 中度用户判定：成功发布 ≥2 套；关闭一次 15 天内不再弹。纯函数便于测试。

  const REVIEW_ASK_KEY = 'review_ask_last_shown'
  const REVIEW_MIN_PUBLISHED = 2
  const REVIEW_COOLDOWN_MS = 15 * 24 * 60 * 60 * 1000

  function shouldAskForReview(publishedCount, lastAskedMs, nowMs = Date.now(),
                              minPublished = REVIEW_MIN_PUBLISHED,
                              cooldownMs = REVIEW_COOLDOWN_MS) {
    if (publishedCount < minPublished) return false
    if (lastAskedMs && nowMs - lastAskedMs < cooldownMs) return false
    return true
  }

  const reviewAskVisible = ref(false)

  function maybeAskForReview() {
    try {
      const published = episodes.value.filter((e) => e.published).length
      const last = Number(localStorage.getItem(REVIEW_ASK_KEY) || 0)
      if (shouldAskForReview(published, last)) {
        reviewAskVisible.value = true
      }
    } catch { /* localStorage 不可用就静默跳过 */ }
  }

  function dismissReviewAsk() {
    reviewAskVisible.value = false
    try { localStorage.setItem(REVIEW_ASK_KEY, String(Date.now())) } catch { /* 忽略 */ }
  }

  // ---- 作品库 / 系列管理 ----

  async function loadSeries() {
    if (!api) return
    const res = await api.send('list_series')
    if (res && res.status === 'ok') seriesList.value = res.data.series || []
  }

  async function saveSeriesList(items) {
    if (!api) return false
    try {
      const res = await api.send('save_series', { series: items })
      if (res && res.status === 'ok') {
        seriesList.value = res.data.series || []
        return true
      }
      lastError.value = (res && res.errors) || [{ message: '系列保存失败' }]
      return false
    } catch (e) {
      lastError.value = [{ message: (e && e.message) || '系列保存失败' }]
      return false
    }
  }

  async function openEpisode(episodeDir) {
    if (!api) return
    selectedEpisode.value = null
    try {
      const res = await api.send('get_episode', { episode_dir: episodeDir })
      if (res && res.status === 'ok') {
        // 数据就绪后再切页：避免详情页挂载守卫（selectedEpisode 为空时弹回）竞态
        selectedEpisode.value = res.data
        phase.value = 'episodeDetail'
        await loadSeries()
      }
    } catch (e) {
      lastError.value = [{ message: (e && e.message) || '加载作品详情失败' }]
      phase.value = 'episodes'
    }
  }

  async function refreshEpisode() {
    if (!api || !selectedEpisode.value) return
    try {
      const res = await api.send('get_episode', { episode_dir: selectedEpisode.value.path })
      if (res && res.status === 'ok') selectedEpisode.value = res.data
      await loadEpisodes()
    } catch { /* 刷新失败保持现状 */ }
  }

  async function updateEpisodeMeta(args) {
    if (!api || !selectedEpisode.value) return false
    try {
      const res = await api.send('update_episode_meta', {
        episode_dir: selectedEpisode.value.path, ...args,
      })
      if (res && res.status === 'ok') {
        await refreshEpisode()
        return res.data || true
      }
      return false
    } catch { return false }
  }

  async function regenEpisodeIntro() {
    if (!api || !selectedEpisode.value) return null
    try {
      const res = await api.send('regen_intro', { episode_dir: selectedEpisode.value.path })
      if (res && res.status === 'ok') {
        await refreshEpisode()
        return res.data
      }
      return null
    } catch { return null }
  }

  async function regenEpisodeAssets() {
    if (!api || !selectedEpisode.value) return null
    try {
      const res = await api.send('regen_assets', { episode_dir: selectedEpisode.value.path })
      if (res && res.status === 'ok') {
        await refreshEpisode()
        return res.data
      }
      return null
    } catch { return null }
  }

  async function publishEpisode(episodeDir) {
    if (!api || !episodeDir) return false
    publishing.value = true
    publishProgress.value = null
    publishResult.value = null
    try {
      const res = await api.send('publish_episode', { episode_dir: episodeDir })
      if (res && res.status === 'ok') {
        publishResult.value = res.data
        return true
      }
      // 发布失败：结果详情（error/step/screenshot）留在 publishResult 就地展示，
      // 不写 lastError —— 避免顶掉成功卡片、误显示成"生成失败"
      // 详情位置两处兼容：主进程正常透传时在 res.data；bridge reject 被主进程
      // 包装后完整结果在 res.raw.data（含 errors 摘要）
      const detail = (res && (res.data || (res.raw && res.raw.data))) || null
      publishResult.value = detail || {
        success: false, step: 'runtime',
        error: (res && (res.error || (res.raw && res.raw.errors && res.raw.errors[0] && res.raw.errors[0].message))) || '发布未完成',
      }
      return false
    } catch (e) {
      // pythonBridge 对 fail 走 reject：详情在 e.data（error/step/screenshot），摘要信息在 e.errors
      publishResult.value = (e && (e.data || (e.raw && e.raw.data))) || {
        success: false, step: 'runtime',
        error: (e && ((e.errors && e.errors[0] && e.errors[0].message) || e.message)) || '发布未完成',
      }
      return false
    } finally {
      publishing.value = false
    }
  }

  async function loadLogs() {
    if (!api) return
    const res = await api.send('get_logs')
    if (res && res.status === 'ok') logs.value = res.data.logs || []
  }

  async function clearLogs() {
    if (!api) return
    await api.send('clear_logs')
    logs.value = []
  }

  async function refreshAgent() {
    if (!api) return
    const [status, prompt] = await Promise.all([
      api.send('agent_status'),
      api.send('agent_prompt'),
    ])
    if (status && status.status === 'ok') agentStatus.value = status.data
    if (prompt && prompt.status === 'ok') agentPrompt.value = prompt.data.prompt || ''
  }

  async function startAgent() {
    if (!api) return false
    const res = await api.send('agent_start', { port: 7432 })
    if (res && res.status === 'ok') {
      agentStatus.value = res.data
      await loadLogs()
      return true
    }
    lastError.value = (res && res.errors) || [{ message: 'Agent 启动失败' }]
    return false
  }

  async function stopAgent() {
    if (!api) return
    const res = await api.send('agent_stop')
    if (res && res.status === 'ok') agentStatus.value = res.data
    await loadLogs()
  }

  // 监听 progress（run 期间更新）+ 底边栏活动日志（任何时候都记录）
  if (api) {
    api.onProgress((ev) => {
      pushActivity({ stage: ev.stage, message: ev.message })
      if (ev.stage === 'install' && installing.value) {
        installLog.value.push(ev.message)
      } else if (publishing.value) {
        publishProgress.value = ev
      } else if (running.value) {
        progress.value = ev
      }
    })
    api.onRestarting(() => {
      running.value = false
      progress.value = null
      pushActivity({ stage: 'SYS', message: '引擎意外退出，正在自动重启…请稍后重试' })
      lastError.value = [{ message: '引擎意外退出，正在自动重启…请稍后重试' }]
    })
    // 更新下载进度 → 底边栏活动流（下载中实时百分比/兆数）
    if (api.onUpdateProgress) {
      api.onUpdateProgress((ev) => {
        if (ev.stage === 'download') {
          pushActivity({
            stage: '更新',
            message: `正在下载新版本… ${ev.percent}%（${ev.receivedMB}/${ev.totalMB} MB）`,
          })
        } else if (ev.stage === 'verify') {
          pushActivity({ stage: '更新', message: '下载完成，正在校验安装包…' })
        }
      })
    }
  }

  return {
    phase, firstRun, prefs, codexStatus, characters, episodes,
    running, progress, lastEpisode, lastError, runStartedAt, activity,
    installing, installLog,
    publishing, publishProgress, publishResult, logs, agentStatus, agentPrompt,
    seriesList, selectedEpisode,
    reviewAskVisible, shouldAskForReview, dismissReviewAsk,
    init, checkCodex, installCodex, loadCharacters, ensureProbabilityDefaults,
    savePrefs, runGenerate, stopRun, loadEpisodes, clearResult, pushActivity,
    loadSeries, saveSeriesList, openEpisode, refreshEpisode,
    updateEpisodeMeta, regenEpisodeIntro, regenEpisodeAssets,
    publishEpisode, loadLogs, clearLogs, refreshAgent, startAgent, stopAgent,
  }
})
