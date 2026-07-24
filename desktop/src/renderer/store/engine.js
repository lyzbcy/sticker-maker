import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useEngineStore = defineStore('engine', () => {
  const phase = ref('launch')   // launch | wizard | main | settings
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

  // 确保 window.api 存在（开发模式 Electron 注入）
  const api = typeof window !== 'undefined' && window.api ? window.api : null

  async function init() {
    if (!api) { phase.value = 'wizard'; return }
    try {
      const res = await api.send('load_prefs')
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
      mode_probs: { single: 0.5, duo: 0.3, trio: 0, quad: 0.2 },
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

  async function loadCharacters() {
    if (!api) return
    const res = await api.send('list_characters')
    if (res && res.status === 'ok') characters.value = res.data.characters || {}
  }

  async function savePrefs(newPrefs) {
    // I2 修复：前端先校验 mode_probs 总和，避免 A 侧 ValueError 静默失败
    const mp = newPrefs.mode_probs || {}
    const sum = (mp.single || 0) + (mp.duo || 0) + (mp.trio || 0) + (mp.quad || 0)
    if (Math.abs(sum - 1) > 0.001) {
      lastError.value = [{ message: `模式概率总和必须为 100%，当前 ${Math.round(sum * 100)}%` }]
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

  // 监听 progress（run 期间更新）
  if (api) {
    api.onProgress((ev) => {
      if (running.value) progress.value = ev
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
    init, checkCodex, loadCharacters, savePrefs, runGenerate, stopRun, loadEpisodes, clearResult,
  }
})
