<template>
  <div class="all-stickers">
    <header class="head">
      <button class="back-btn" @click="store.phase = 'episodes'">← 返回作品库</button>
      <h2>🖼️ 全部表情（{{ shownTotal }} 张 · {{ shownGroups.length }} 弹）</h2>
      <button class="copy-btn" :disabled="copying" @click="copyAll">
        {{ copying ? '生成中…' : '📋 复制打分与 Prompt' }}
      </button>
      <span v-if="copyTip" class="copy-tip">{{ copyTip }}</span>
    </header>

    <section v-if="remakeText" class="remake-plan">
      <h3>精品定制重制 · 免费发布</h3><p>原图与评分不改。复制逐图方案交给生图工具重绘，确认新图后导入新作品。</p>
      <p role="status">{{ duplicateMessage }}</p>
      <textarea v-model="remakeText" rows="12" aria-label="精品重绘提示词" style="width:100%;box-sizing:border-box"></textarea>
      <button class="copy-btn" @click="copyRemake">复制重制提示词</button>
      <button class="copy-btn" @click="remakeText = ''">关闭</button>
    </section>
    <div class="filters">
      <label class="f-item">
        <span class="f-label">系列</span>
        <select v-model="seriesSel" class="f-select">
          <option value="">全部系列</option>
          <option v-for="s in seriesList" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="f-item" title="留空 = 不限；只填一头也行">
        <span class="f-label">第</span>
        <input v-model.number="fromNo" type="number" min="0" class="f-num" placeholder="起" />
        <span class="f-label">—</span>
        <input v-model.number="toNo" type="number" min="0" class="f-num" placeholder="止" />
        <span class="f-label">弹（导出范围）</span>
      </label>
      <span class="f-hint">选中系列后按弹数从高到低排列</span>
    </div>
    <p class="hint">跨所有作品的表情总览：直接打分+备注（与详情页同一数据库）；点星星评分，备注框写问题。</p>

    <section v-for="g in shownGroups" :key="g.episode_dir" class="group">
      <div class="group-head">
        <h3>{{ g.album_name }}</h3>
        <span class="rated-count">{{ Object.keys(g.ratings || {}).length }}/{{ g.stickers.length }} 已打分</span>
      </div>
      <div class="grid">
        <div v-for="st in g.stickers" :key="st.path" class="cell">
          <img :src="fileUrl(st.path)" loading="lazy" :title="st.meaning" @error="onErr" />
          <span class="meaning">{{ st.meaning }}</span>
          <button class="copy-btn" @click="remake(g, st)">精品重制方案</button>
          <div class="stars">
            <button v-for="s in 5" :key="s" class="star"
                    :class="{ on: (g.ratings[st.meaning] || {}).score >= s }"
                    @click="rate(g, st.meaning, s)">★</button>
          </div>
          <input class="note" :value="(g.ratings[st.meaning] || {}).note || ''"
                 placeholder="备注问题…" @change="note(g, st.meaning, $event)" />
        </div>
      </div>
    </section>
    <p v-if="!shownGroups.length" class="empty">还没有作品</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useEngineStore } from '../store/engine'
import { remakePrompt } from '../utils/featuredRemake'

const store = useEngineStore()
const remakeText = ref(''), duplicateMessage = ref('')
let remakeGeneration = 0
async function remake(group, sticker) {
  const generation = ++remakeGeneration
  const rating = group.ratings?.[sticker.meaning]
  remakeText.value = remakePrompt(group, sticker, rating ? `人工分 ${rating.score ?? '未填'}；${rating.note || ''}` : '')
  duplicateMessage.value = '正在只读检查本地字节重复…'
  try {
    const r = await window.api.send('check_sticker_duplicate', { path:sticker.path })
    if (generation !== remakeGeneration) return
    duplicateMessage.value = r?.status === 'ok' ? `发现 ${r.data.matches.length} 份字节相同图片（检查 ${r.data.checked} 张，跳过 ${r.data.skipped} 张）；不是平台相似度判定。` : (r?.errors?.[0]?.message || '重复检查失败')
  } catch(e) { if(generation === remakeGeneration) duplicateMessage.value = e.message }
}
async function copyRemake() {
  try { await navigator.clipboard.writeText(remakeText.value); duplicateMessage.value = '逐图重制提示词已复制；请生成新图并人工验收。' }
  catch { duplicateMessage.value = '请在文本框中手动选择复制。' }
}
const groups = ref([])
const total = ref(0)
const seriesList = ref([])
const seriesSel = ref('')      // '' = 全部系列；默认加载后自动选中默认系列
const fromNo = ref(null)       // 导出弹数范围（只影响复制，不影响浏览）
const toNo = ref(null)
const copying = ref(false)
const copyTip = ref('')
const timers = {}

onBeforeUnmount(async () => { await flushAllPending() })
onMounted(async () => {
  if (!window.api) return
  const res = await window.api.send('list_all_stickers', {})
  if (res?.status === 'ok') {
    groups.value = res.data.groups
    total.value = res.data.total
    seriesList.value = res.data.series || []
    // 默认选中用户设置的默认系列（无则作品最多的系列）
    const def = res.data.default_series
    if (def && seriesList.value.includes(def)) seriesSel.value = def
  }
})

// 系列筛选 + 选中系列时按弹数从高到低（最新单在前）
const shownGroups = computed(() => {
  let gs = groups.value
  if (seriesSel.value) {
    gs = gs.filter(g => g.series_name === seriesSel.value)
    gs = [...gs].sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
  }
  return gs
})
const shownTotal = computed(() =>
  shownGroups.value.reduce((n, g) => n + g.stickers.length, 0))

function fileUrl(p) {
  return 'file:///' + String(p || '').replace(/\\/g, '/')
}
function onErr(e) { e.target.style.visibility = 'hidden' }

// 打分/备注 → 对应单的 rating.json（与详情页同一数据库；400ms 防抖合并整单保存）
function rate(g, meaning, score) {
  const cur = (g.ratings[meaning] || {}).score
  const note = (g.ratings[meaning] || {}).note || ''
  g.ratings = { ...g.ratings, [meaning]: { score: cur === score ? 0 : score, note } }
  queueSave(g)
}
function note(g, meaning, ev) {
  const score = (g.ratings[meaning] || {}).score || 0
  g.ratings = { ...g.ratings, [meaning]: { score, note: ev.target.value } }
  queueSave(g)
}
const pending = {}   // episode_dir -> 待落盘的打分快照（2026-09-11 防丢加固）
function queueSave(g) {
  // 打分快照先进 pending：即使防抖窗口内切页/关窗，卸载钩子也会强制落盘
  pending[g.episode_dir] = {
    overall: g.overall || null,
    ratings: JSON.parse(JSON.stringify(g.ratings || {})),
  }
  clearTimeout(timers[g.episode_dir])
  timers[g.episode_dir] = setTimeout(() => flushSave(g.episode_dir), 400)
}
async function flushSave(dir) {
  const snap = pending[dir]
  if (!snap || !window.api) return
  delete pending[dir]
  try {
    const res = await window.api.send('save_rating', {
      episode_dir: dir,
      overall: snap.overall,
      note: '',
      ratings: snap.ratings,
    })
    if (res?.status !== 'ok') {
      copyTip.value = '保存失败：' + (res?.errors?.[0]?.message || '未知')
    }
  } catch (e) {
    copyTip.value = '保存失败：' + (e.message || e)
  }
}
async function flushAllPending() {
  const dirs = Object.keys(pending)
  for (const dir of dirs) await flushSave(dir)
}
// 关窗前强制落盘（防抖窗口内的打分不再无声丢失）
window.addEventListener('beforeunload', () => { if (Object.keys(pending).length) flushAllPending() })

async function copyAll() {
  if (!window.api) return
  copying.value = true
  copyTip.value = ''
  try {
    // 导出跟随当前系列选择 + 弹数范围（from/to 留空 = 不限）
    const res = await window.api.send('build_all_ratings_prompt', {
      series: seriesSel.value || null,
      from_no: fromNo.value || null,
      to_no: toNo.value || null,
    })
    if (res?.status === 'ok' && res.data?.text) {
      const clip = await window.api.copyText(res.data.text)
      copyTip.value = (clip && clip.ok)
        ? `✓ 已导出 ${res.data.count} 弹到 ${res.data.folder || 'rating_export'}，路径已复制，粘贴给 AI 即可`
        : '复制失败：剪贴板不可用'
    } else {
      copyTip.value = res?.errors?.[0]?.message || '没有可复制的打分'
    }
  } finally {
    copying.value = false
  }
}
</script>

<style scoped>
.all-stickers { padding: 18px 22px 60px; max-width: 1280px; margin: 0 auto; }
.head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.back-btn { border: 1px solid #ddd; background: white; border-radius: 999px;
  padding: 8px 14px; cursor: pointer; font-size: 13px; }
.copy-btn { border: 0; background: var(--forest, #2e4a34); color: white;
  border-radius: 999px; padding: 9px 16px; font-weight: 800; cursor: pointer; font-size: 13px; }
.copy-btn:disabled { opacity: .6; cursor: wait; }
.copy-tip { font-size: 12px; color: var(--muted, #888); }
.filters { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  margin-top: 12px; padding: 10px 14px; background: #faf8f4;
  border: 1.5px solid #eee6da; border-radius: 12px; }
.f-item { display: flex; align-items: center; gap: 6px; }
.f-label { font-size: 12.5px; color: #666; font-weight: 600; }
.f-select { border: 1px solid #ddd; border-radius: 8px; padding: 6px 8px;
  font-size: 13px; background: white; min-width: 150px; }
.f-num { width: 64px; border: 1px solid #ddd; border-radius: 8px;
  padding: 6px 6px; font-size: 13px; }
.f-hint { font-size: 11.5px; color: #aaa; }
.hint { color: var(--muted, #888); font-size: 12.5px; margin: 10px 0 4px; }
.group { margin: 18px 0; }
.group-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.group-head h3 { margin: 0; font-size: 15px; }
.rated-count { font-size: 12px; color: var(--muted, #888); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 10px; }
.cell { background: white; border-radius: 12px; padding: 8px; text-align: center;
  box-shadow: 0 1px 6px rgba(0,0,0,.06); }
.cell img { width: 96px; height: 96px; object-fit: contain; }
.meaning { display: block; font-size: 11.5px; color: #555; margin: 2px 0; }
.stars { display: flex; justify-content: center; gap: 1px; }
.star { border: 0; background: none; color: #ddd; font-size: 15px; cursor: pointer; padding: 0 1px; }
.star.on { color: #f5a623; }
.note { width: 92%; border: 1px solid #eee; border-radius: 8px; font-size: 11px;
  padding: 4px 6px; margin-top: 4px; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
