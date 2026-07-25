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

  // 确保 window.api 存在（开发模式 Electron 注入）
  const api = typeof window !== 'undefined' && window.api ? window.api : null

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
      const res = await api.send('save_prefs', { prefs: newPrefs })
      if (res && res.status === 'ok') {
        prefs.value = newPrefs
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

  async function runGenerate() {
    if (!api) return
    running.value = true
    progress.value = null
    lastError.value = null
    lastEpisode.value = null
    try {
      const res = await api.send('run')
      if (res && res.status === 'ok') {
        lastEpisode.value = res.data
      } else {
        lastError.value = (res && res.errors) || [{ message: (res && res.aborted_reason) || '运行失败' }]
      }
    } catch (e) {
      lastError.value = (e && e.errors) || [{ message: (e && e.message) || '运行失败' }]
    } finally {
      running.value = false
      progress.value = null
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
  }

  async function publishEpisode(episodeDir) {
    if (!api || !episodeDir) return false
    publishing.value = true
    publishProgress.value = null
    publishResult.value = null
    lastError.value = null
    try {
      const res = await api.send('publish_episode', { episode_dir: episodeDir })
      if (res && res.status === 'ok') {
        publishResult.value = res.data
        return true
      }
      publishResult.value = (res && res.data) || null
      lastError.value = (res && res.errors) || [{ message: '发布未完成' }]
      return false
    } catch (e) {
      lastError.value = (e && e.errors) || [{ message: (e && e.message) || '发布未完成' }]
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

  // 监听 progress（run 期间更新）
  if (api) {
    api.onProgress((ev) => {
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
      lastError.value = [{ message: '引擎意外退出，正在自动重启…请稍后重试' }]
    })
  }

  return {
    phase, firstRun, prefs, codexStatus, characters, episodes,
    running, progress, lastEpisode, lastError,
    installing, installLog,
    publishing, publishProgress, publishResult, logs, agentStatus, agentPrompt,
    init, checkCodex, installCodex, loadCharacters, ensureProbabilityDefaults,
    savePrefs, runGenerate, stopRun, loadEpisodes, clearResult,
    publishEpisode, loadLogs, clearLogs, refreshAgent, startAgent, stopAgent,
  }
})
