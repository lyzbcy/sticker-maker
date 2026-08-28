<template>
  <div class="detail" v-if="ep">
    <header>
      <button class="back" @click="store.phase = 'episodes'">← 作品库</button>
      <h2 class="title">{{ ep.meta.album_name || ep.name }}</h2>
      <span class="ep-badge published" v-if="ep.meta.published">✓ 已发布</span>
    </header>

    <div class="body">
      <!-- 名称与系列 -->
      <section class="card">
        <h3 class="card-title">名称</h3>
        <!-- 专辑名 -->
        <div class="name-row">
          <input v-model="albumName" class="name-input" placeholder="专辑名（最多 30 字）" maxlength="30" />
          <button class="btn-sm" :disabled="!albumName || albumName === (ep.meta.album_name || '')"
                  @click="saveName">保存</button>
        </div>
        <!-- 系列归属：状态 + 修改，一层一层来 -->
        <div class="series-block">
          <div class="series-status">
            <template v-if="ep.meta.series_name">
              归属系列：<strong>{{ ep.meta.series_name }}</strong>
              <span class="series-num">编号 {{ ep.meta.number }}</span>
            </template>
            <template v-else>
              <span class="muted">未编入系列——编入后自动按系列编号命名（如「周思涵做表情 61」）</span>
            </template>
          </div>
          <div class="name-row" v-if="!showNewSeries">
            <select v-model="pickedSeries" class="name-input series-select">
              <option value="">— 选择要编入的系列 —</option>
              <option v-for="s in store.seriesList" :key="s.id" :value="s.id">
                {{ s.name }}（将命名为「{{ s.name }} {{ s.next_number }}」）
              </option>
            </select>
            <button class="btn-sm" :disabled="!pickedSeries" @click="assignSeries">编入</button>
            <button class="link-btn" @click="showNewSeries = true">+ 新建系列</button>
          </div>
          <!-- 新建系列（点开后独占一层，不再挤在一起） -->
          <div class="new-series-box" v-else>
            <p class="new-series-title">新建系列并编入本作品：</p>
            <div class="name-row">
              <input v-model="newSeriesName" class="name-input" placeholder="系列名称，如：周思涵做表情" />
              <input v-model.number="newSeriesStart" type="number" min="1" class="num-input" placeholder="起始编号" />
            </div>
            <div class="name-row">
              <button class="btn-sm" :disabled="!newSeriesName" @click="createSeries">创建并编入</button>
              <button class="btn-sm btn-reset" @click="showNewSeries = false">取消</button>
            </div>
          </div>
        </div>
        <!-- 改名/编入后，介绍里还是旧名称 → 提示重新生成 -->
        <p v-if="introStale" class="stale-hint">
          ⚠ 介绍还是用旧名称「{{ introOldName }}」生成的，建议点下方「AI 重新生成」
        </p>
      </section>

      <!-- 介绍 -->
      <section class="card">
        <h3 class="card-title">介绍（{{ intro.length }}/80）</h3>
        <textarea v-model="intro" class="intro-textarea" maxlength="80"
                  placeholder="一句话介绍这组表情（保存后随发布一起提交）"></textarea>
        <div class="row-actions">
          <button class="btn-sm" :disabled="intro === (ep.meta.intro || '')" @click="saveIntro">保存介绍</button>
          <button class="btn-sm btn-ai" :disabled="regenIntroBusy" @click="regenIntro">
            {{ regenIntroBusy ? 'AI 生成中…' : '✨ AI 重新生成（用系列提示词）' }}
          </button>
        </div>
      </section>

      <!-- 素材 -->
      <section class="card">
        <h3 class="card-title">横幅 / 封面 / 图标</h3>
        <div class="assets-row">
          <div class="asset" v-for="kind in ['banner', 'cover', 'icon']" :key="kind">
            <img v-if="ep[kind]" :src="fileUrl(ep[kind])" class="asset-img" :class="kind" />
            <div v-else class="asset-img placeholder">{{ assetLabel(kind) }}缺失</div>
            <div class="asset-controls">
              <select v-model="modes[kind]" class="mode-select">
                <option value="auto">标准拼贴</option>
                <option value="pick" v-if="kind !== 'banner'">从本组选图</option>
                <option value="custom">自定义上传</option>
                <option value="role" v-if="hasRoleMap">角色默认映射</option>
              </select>
              <select v-if="modes[kind] === 'pick'" v-model.number="picks[kind]" class="mode-select">
                <option v-for="(st, i) in ep.stickers" :key="i" :value="i">第 {{ i + 1 }} 张 · {{ st.meaning }}</option>
              </select>
              <button v-if="modes[kind] === 'custom'" class="btn-sm" @click="pickCustomFile(kind)">选择文件…</button>
              <span v-if="customPaths[kind]" class="custom-path">{{ shortPath(customPaths[kind]) }}</span>
            </div>
          </div>
        </div>
        <div class="row-actions">
          <button class="btn-sm" :disabled="regenAssetsBusy" @click="regenAssets">
            {{ regenAssetsBusy ? '生成中…' : '↻ 按以上设置重新生成素材' }}
          </button>
          <span v-if="assetWarnings.length" class="warn-text">{{ assetWarnings.join('；') }}</span>
        </div>
      </section>

      <!-- 表情预览 + 打分（打分自动存 rating.json，可整文件发给 AI 反哺优化 prompt） -->
      <section class="card">
        <h3 class="card-title">
          表情（{{ ep.stickers.length }} 张）<span class="muted">角色：{{ ep.characters.join('、') || '—' }}</span>
          <span class="rate-hint">👆 点星星打分（1-5，自动保存；评分文件可发给 AI 优化 prompt）</span>
        </h3>
        <div class="sticker-grid">
          <div v-for="(st, i) in ep.stickers" :key="st.file" class="sticker-cell" :title="st.meaning">
            <img :src="fileUrl(st.path)" />
            <span class="meaning">{{ st.meaning }}</span>
            <span class="idx">{{ i + 1 }}</span>
            <div class="stars">
              <button v-for="s in 5" :key="s" class="star"
                      :class="{ on: (ratings[st.meaning] || {}).score >= s }"
                      @click="rate(st.meaning, s)" :title="`${s} 分`">★</button>
            </div>
            <input class="rate-note" title="备注：这张哪里有问题/哪里好"
                   :value="(ratings[st.meaning] || {}).note || ''"
                   placeholder="备注问题…" @change="noteRate(st.meaning, $event)" />
          </div>
        </div>
        <div class="overall-row">
          <span class="overall-label">整组总评：</span>
          <button v-for="s in 5" :key="s" class="star big"
                  :class="{ on: (overall || 0) >= s }"
                  @click="overall = (overall === s ? null : s); saveRating()">{{ s }}</button>
          <input class="overall-note" v-model="note" placeholder="一句话总评（哪里好/哪里不行，AI 反哺时用得上）"
                 @change="saveRating" />
          <span v-if="ratingSavedAt" class="saved-tip">✓ {{ ratingSavedAt }}</span>
          <button class="copy-feedback-btn" :disabled="copyingFeedback" @click="() => copyFeedback()">
            {{ copyingFeedback ? '生成中…' : '📋 一键复制 AI 反哺提示词' }}
          </button>
        </div>
      </section>

      <!-- 发布 -->
      <section class="card">
        <h3 class="card-title">发布</h3>
        <div class="row-actions">
          <button class="publish-btn" :disabled="store.publishing" @click="publish">
            {{ store.publishing ? '正在提交…' : (ep.meta.published ? '再次提交微信' : '一键提交微信') }}
          </button>
          <button class="btn-sm btn-reset" @click="openFinder">在文件夹中显示</button>
          <!-- 弹药闭环：本组贴纸去重回流参考图库（已上架作品=市场验证过的良品） -->
          <button class="btn-sm" :disabled="replenishing" @click="replenishRefs">
            {{ replenishing ? '回流中…' : '回流参考图库' }}
          </button>
        </div>
        <p v-if="replenishResult" class="pub-ok" style="font-size: 12px;">
          {{ replenishResult }}
        </p>
        <div v-if="store.publishProgress" class="pub-progress">{{ store.publishProgress.message }}</div>
        <p v-if="publishOk" class="pub-ok">✓ 已提交到微信表情开放平台</p>
        <div v-else-if="publishFail" class="pub-fail">
          <p class="pub-fail-title">发布未完成（{{ publishFail.step }}）</p>
          <p class="pub-fail-detail">{{ publishFail.error || '未知原因' }}</p>
          <ul v-if="publishFailWarnings.length" class="pub-warnings">
            <li v-for="(w, i) in publishFailWarnings" :key="i">⚠ {{ w }}</li>
          </ul>
          <p v-if="publishFail.screenshot" class="pub-shot">现场截图：{{ publishFail.screenshot }}</p>
        </div>
      </section>
    </div>
  </div>
  <div v-else class="detail loading">
    <div class="center-pill">加载作品详情…</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useEngineStore } from '../store/engine'

const store = useEngineStore()
const ep = computed(() => store.selectedEpisode)

const albumName = ref('')
const intro = ref('')
const pickedSeries = ref('')
const showNewSeries = ref(false)
const newSeriesName = ref('')
const newSeriesStart = ref(1)
const regenIntroBusy = ref(false)
const regenAssetsBusy = ref(false)
const assetWarnings = ref([])
const modes = ref({ banner: 'auto', cover: 'auto', icon: 'auto' })
const picks = ref({ banner: 0, cover: 0, icon: 0 })
const customPaths = ref({})

onMounted(() => { if (!store.selectedEpisode) store.phase = 'episodes' })

// ---- 打分（自动存 rating.json）----
const ratings = ref({})
const overall = ref(null)
const note = ref('')
const ratingSavedAt = ref('')
let ratingTimer = null

async function loadRating() {
  if (!ep.value?.path || !window.api) return
  try {
    const res = await window.api.send('get_rating', { episode_dir: ep.value.path })
    if (res?.status === 'ok') {
      ratings.value = res.data.ratings || {}
      overall.value = res.data.overall ?? null
      note.value = res.data.note || ''
    }
  } catch { /* 静默 */ }
}
function rate(meaning, score) {
  const cur = (ratings.value[meaning] || {}).score
  ratings.value = { ...ratings.value, [meaning]: { score: cur === score ? 0 : score, note: '' } }
  saveRating()
}
function noteRate(meaning, ev) {
  const cur = ratings.value[meaning] || {}
  ratings.value = { ...ratings.value, [meaning]: { score: cur.score || 0, note: ev.target.value } }
  saveRating()
}

const copyingFeedback = ref(false)
async function copyFeedback() {
  if (!ep.value?.path || !window.api) return
  copyingFeedback.value = true
  try {
    const res = await window.api.send('build_feedback_prompt', { episode_dir: ep.value.path })
    if (res?.status === 'ok' && res.data && res.data.text) {
      const clip = await window.api.copyText(res.data.text)
      ratingSavedAt.value = (clip && clip.ok)
        ? '已复制反哺提示词（' + clip.length + ' 字），粘贴给 AI 即可'
        : '复制失败：剪贴板不可用'
    } else {
      ratingSavedAt.value = '生成失败：' + (res?.errors?.[0]?.message || '返回内容为空')
    }
  } finally {
    copyingFeedback.value = false
  }
}

function saveRating() {
  if (!ep.value?.path || !window.api) return
  clearTimeout(ratingTimer)
  ratingTimer = setTimeout(async () => {
    try {
      const res = await window.api.send('save_rating', {
        episode_dir: ep.value.path,
        ratings: JSON.parse(JSON.stringify(ratings.value)),
        overall: overall.value, note: note.value,
      })
      if (res?.status === 'ok') ratingSavedAt.value = '已保存 ' + new Date().toLocaleTimeString()
      else ratingSavedAt.value = '保存失败：' + (res?.errors?.[0]?.message || '未知')
    } catch (e) { ratingSavedAt.value = '保存异常：' + (e?.message || e) }
  }, 400)
}
loadRating()
watch(ep, (v) => {
  if (v) {
    albumName.value = v.meta.album_name || ''
    intro.value = v.meta.intro || ''
    pickedSeries.value = v.meta.series_id || ''
    modes.value = {
      banner: v.meta.banner_mode || 'auto',
      cover: v.meta.cover_mode || 'auto',
      icon: v.meta.icon_mode || 'auto',
    }
    picks.value = { banner: 0, cover: v.meta.cover_pick || 0, icon: 0 }
    customPaths.value = {
      banner: v.meta.banner_custom || '',
      cover: v.meta.cover_custom || '',
      icon: v.meta.icon_custom || '',
    }
  }
}, { immediate: true })

const exampleSeriesName = computed(() =>
  (store.seriesList[0] && store.seriesList[0].name) || '系列名')
// 介绍是否还是旧名称生成的（改名/编入后提示重新生成）
const introOldName = ref('')
const introStale = computed(() =>
  !!introOldName.value &&
  !!intro.value &&
  intro.value.includes(introOldName.value) &&
  !intro.value.includes(albumName.value || ep.value?.meta?.album_name || ''))
watch(ep, (v) => { if (v) introOldName.value = extractOldName(v.meta.intro || '') }, { immediate: true })
function extractOldName(text) {
  const m = text.match(/《(.+?)》/)
  return m ? m[1] : ''
}
const hasRoleMap = computed(() => {
  const s = store.seriesList.find(x => x.id === (ep.value?.meta?.series_id || pickedSeries.value))
  return !!(s && s.role_asset_map && Object.keys(s.role_asset_map).length)
})

const publishOk = computed(() => !store.publishing && store.publishResult?.success === true)
const publishFail = computed(() =>
  !store.publishing && store.publishResult && store.publishResult.success === false
    ? store.publishResult : null)
const publishFailWarnings = computed(() => publishFail.value?.warnings || [])

function fileUrl(p) { return window.api ? window.api.toFileUrl(p) : p }
function shortPath(p) { const s = String(p || ''); return s.length > 30 ? '…' + s.slice(-28) : s }
function assetLabel(kind) { return { banner: '横幅', cover: '封面', icon: '图标' }[kind] }

async function saveName() {
  await store.updateEpisodeMeta({ album_name: albumName.value })
}
async function assignSeries() {
  await store.updateEpisodeMeta({ assign_series_id: pickedSeries.value })
  await store.loadSeries()   // 刷新各系列"下一编号"显示
}
async function createSeries() {
  const ok = await store.saveSeriesList([
    ...store.seriesList.map(s => ({
      id: s.id, name: s.name, start_number: s.start_number,
      intro_prompt: s.intro_prompt, role_asset_map: s.role_asset_map,
    })),
    { name: newSeriesName.value, start_number: newSeriesStart.value || 1 },
  ])
  if (ok) {
    const created = store.seriesList[store.seriesList.length - 1]
    if (created) await store.updateEpisodeMeta({ assign_series_id: created.id })
    showNewSeries.value = false
    newSeriesName.value = ''
    newSeriesStart.value = 1
  }
}
async function saveIntro() {
  await store.updateEpisodeMeta({ intro: intro.value })
}
async function regenIntro() {
  regenIntroBusy.value = true
  try {
    const r = await store.regenEpisodeIntro()
    if (r) intro.value = r.intro || intro.value
  } finally { regenIntroBusy.value = false }
}
async function pickCustomFile(kind) {
  if (!window.api) return
  const res = await window.api.selectFile()
  if (res && !res.canceled && res.path) customPaths.value[kind] = res.path
}
async function regenAssets() {
  regenAssetsBusy.value = true
  assetWarnings.value = []
  try {
    const r = await store.updateEpisodeMeta({
      regen_assets: true,
      banner_mode: modes.value.banner, banner_custom: customPaths.value.banner || '',
      cover_mode: modes.value.cover, cover_pick: picks.value.cover,
      cover_custom: customPaths.value.cover || '',
      icon_mode: modes.value.icon, icon_custom: customPaths.value.icon || '',
    })
    if (r && r.warnings) assetWarnings.value = r.warnings
  } finally { regenAssetsBusy.value = false }
}
async function publish() {
  if (ep.value?.path) await store.publishEpisode(ep.value.path)
}
async function openFinder() {
  if (ep.value?.path && window.api) {
    await window.api.send('open_in_finder', { path: ep.value.path })
  }
}

// ---- 回流参考图库（弹药闭环） ----
const replenishing = ref(false)
const replenishResult = ref('')
async function replenishRefs() {
  if (!ep.value?.path || !window.api) return
  replenishing.value = true
  replenishResult.value = ''
  try {
    const res = await window.api.send('replenish_refs', { episode_dir: ep.value.path })
    if (res && res.status === 'ok') {
      const d = res.data
      replenishResult.value =
        `✓ 已回流 ${d.imported.length} 张进参考图库（现共 ${d.library_count} 张）` +
        (d.skipped.length ? `；${d.skipped.length} 张与库内雷同已跳过` : '')
    } else {
      replenishResult.value = '回流失败：' + (res?.errors?.[0]?.message || '未知原因')
    }
  } finally {
    replenishing.value = false
  }
}
</script>

<style scoped>
.detail { padding: 32px; max-width: 860px; margin: 0 auto; }
.loading { display: grid; place-items: center; min-height: 50vh; }
.center-pill { padding: 14px 28px; border-radius: var(--r-pill); background: var(--card); box-shadow: var(--shadow-card); color: var(--muted); }

header { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }
.back {
  background: var(--card); border: 1.5px solid var(--paper); border-radius: var(--r-pill);
  padding: 8px 18px; color: var(--forest); cursor: pointer; font-weight: 600; font-size: 14px;
  box-shadow: var(--shadow-soft); transition: all .15s ease;
}
.back:hover { border-color: var(--sage); transform: translateX(-2px); }
.title { margin: 0; font-family: var(--font-head); font-size: 21px; font-weight: 700; color: var(--ink); }
.ep-badge.published {
  font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: var(--r-pill);
  background: rgba(175, 205, 168, .3); color: var(--correct);
}

.body { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--card); border: 1.5px solid var(--paper); border-radius: var(--r-card);
  padding: 22px 24px; box-shadow: var(--shadow-card);
}
.card-title {
  margin: 0 0 14px; padding-bottom: 10px; border-bottom: 1.5px dashed var(--paper);
  font-family: var(--font-head); font-size: 15px; font-weight: 700; color: var(--forest);
  display: flex; align-items: baseline; gap: 10px;
}
.muted { color: var(--muted-soft); font-size: 12px; font-weight: 400; }

.name-row { display: flex; gap: 10px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
.name-input {
  flex: 1; min-width: 220px; max-width: 420px;
  padding: 10px 14px; border: 1.5px solid var(--paper); border-radius: var(--r-md);
  background: var(--bg-cream); font-size: 13.5px; color: var(--ink); font-family: var(--font-body);
}
.name-input:focus { outline: none; border-color: var(--sage); }
.num-input {
  width: 100px; padding: 10px 12px; border: 1.5px solid var(--paper);
  border-radius: var(--r-md); background: var(--bg-cream); font-size: 13.5px; color: var(--ink);
}
.series-block { margin-top: 10px; padding-top: 12px; border-top: 1px dashed var(--paper); }
.series-status { font-size: 13px; color: var(--ink); margin-bottom: 8px; }
.series-num {
  margin-left: 8px; font-size: 11px; font-weight: 700; color: var(--forest);
  background: var(--marker); padding: 2px 8px; border-radius: var(--r-pill);
}
.series-select { max-width: 340px; }
.new-series-box {
  margin-top: 8px; padding: 14px; border-radius: var(--r-md);
  background: var(--bg-cream); border: 1.5px dashed var(--line);
}
.new-series-title { margin: 0 0 8px; font-size: 12.5px; color: var(--muted); font-weight: 600; }
.stale-hint {
  margin: 10px 0 0; padding: 8px 12px; border-radius: var(--r-sm);
  background: rgba(245, 224, 138, .35); color: #8a6d1a; font-size: 12.5px;
}
.new-series { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 6px; }
.link-btn {
  background: none; border: none; color: var(--forest); font-size: 12.5px;
  cursor: pointer; padding: 4px 0; font-weight: 600;
}
.link-btn:hover { text-decoration: underline; }
.series-row { margin-top: 12px; }
.field-label { display: block; font-size: 12.5px; color: var(--muted); margin-bottom: 2px; }

.intro-textarea {
  width: 100%; min-height: 84px; resize: vertical;
  padding: 12px 14px; border: 1.5px solid var(--paper); border-radius: var(--r-md);
  background: var(--bg-cream); font-size: 13.5px; line-height: 1.7; color: var(--ink);
  font-family: var(--font-body);
}
.intro-textarea:focus { outline: none; border-color: var(--sage); }

.row-actions { display: flex; gap: 10px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
.btn-sm {
  padding: 9px 16px; border: 1.5px solid var(--forest); border-radius: var(--r-pill);
  background: var(--card); color: var(--forest); cursor: pointer;
  font-weight: 600; font-size: 12.5px; white-space: nowrap; transition: all .15s ease;
}
.btn-sm:hover:not(:disabled) { background: var(--forest); color: var(--white); }
.btn-sm:disabled { opacity: .45; cursor: not-allowed; }
.btn-sm.btn-reset { border-color: var(--line); color: var(--muted); }
.btn-sm.btn-reset:hover:not(:disabled) { background: var(--paper); color: var(--ink); }
.btn-ai { border-color: var(--marker); background: rgba(245, 224, 138, .25); }
.btn-ai:hover:not(:disabled) { background: var(--marker); color: var(--ink); }

.assets-row { display: flex; gap: 18px; flex-wrap: wrap; }
.asset { display: flex; flex-direction: column; gap: 8px; }
.asset-img {
  border: 1.5px solid var(--paper); border-radius: var(--r-md); background: var(--bg-cream);
  object-fit: cover;
}
.asset-img.banner { width: 224px; height: 119px; }   /* 750:400 比例 */
.asset-img.cover, .asset-img.icon { width: 96px; height: 96px; }
.asset-img.placeholder {
  display: grid; place-items: center; color: var(--muted-faint); font-size: 12px;
  width: 150px; height: 100px;
}
.asset-controls { display: flex; flex-direction: column; gap: 6px; max-width: 224px; }
.mode-select {
  padding: 7px 10px; border: 1.5px solid var(--paper); border-radius: var(--r-sm);
  background: var(--bg-cream); font-size: 12px; color: var(--ink); font-family: var(--font-body);
}
.custom-path { font-size: 11px; color: var(--muted-soft); word-break: break-all; }
.warn-text { color: var(--brick); font-size: 12px; }

.sticker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 10px; }
.rate-hint { font-size: 11px; color: var(--muted-soft); font-weight: 500; margin-left: 8px; }
.stars { display: flex; gap: 1px; justify-content: center; margin-top: 2px; }
.star {
  border: none; background: none; padding: 0; font-size: 15px; line-height: 1;
  color: var(--line); cursor: pointer; transition: transform .1s ease, color .1s ease;
}
.star.on { color: #f5a623; }
.star:hover { transform: scale(1.25); }
.star.big { font-size: 16px; padding: 2px 6px; border: 1px solid var(--paper); border-radius: 6px; margin-right: 4px; background: var(--card); }
.star.big.on { border-color: #f5a623; }
.overall-row {
  display: flex; align-items: center; gap: 4px; margin-top: 14px; flex-wrap: wrap;
  padding: 10px 12px; background: var(--bg-cream, #faf6eb); border-radius: 10px;
}
.overall-label { font-size: 13px; font-weight: 700; color: var(--ink); }
.overall-note {
  flex: 1; min-width: 220px; padding: 7px 12px; border: 1.5px solid var(--paper);
  border-radius: 8px; font-size: 12.5px; background: var(--card);
}
.saved-tip { font-size: 11px; color: var(--correct); }
.rate-note {
  width: 100%; margin-top: 3px; padding: 3px 6px; font-size: 10.5px;
  border: 1px solid var(--paper); border-radius: 6px; background: var(--card);
  box-sizing: border-box;
}
.rate-note:focus { outline: none; border-color: var(--sage); }
.copy-feedback-btn {
  margin-left: auto; padding: 7px 14px; border-radius: 999px; border: none;
  background: var(--forest); color: #fff; font-size: 12px; font-weight: 700;
  cursor: pointer; box-shadow: var(--shadow-btn);
}
.copy-feedback-btn:disabled { opacity: .6; cursor: wait; }
.sticker-cell {
  position: relative; background: var(--bg-cream); border: 1.5px solid var(--paper);
  border-radius: var(--r-md); padding: 6px; text-align: center;
}
.sticker-cell img { width: 100%; aspect-ratio: 1; object-fit: contain; }
.meaning { display: block; font-size: 11px; color: var(--muted); margin-top: 3px; }
.idx {
  position: absolute; top: 4px; left: 4px; font-size: 9px; font-weight: 700;
  background: rgba(30, 58, 36, .65); color: white; border-radius: 6px; padding: 1px 5px;
}

.publish-btn {
  padding: 12px 30px; border: none; border-radius: var(--r-pill);
  background: var(--forest); color: var(--white); cursor: pointer;
  font-family: var(--font-head); font-weight: 700; font-size: 14px;
  box-shadow: var(--shadow-btn); transition: all .15s ease;
}
.publish-btn:hover:not(:disabled) { background: var(--forest-hover); transform: translateY(-1px); }
.publish-btn:disabled { opacity: .6; cursor: wait; }

.pub-progress { margin-top: 12px; color: var(--forest); font-size: 13px; font-weight: 600; }
.pub-ok { margin: 12px 0 0; color: var(--correct); font-size: 13.5px; font-weight: 700; }
.pub-fail {
  margin-top: 12px; padding: 12px 16px; border-radius: var(--r-md);
  background: rgba(181, 72, 42, .07); border: 1.5px solid rgba(181, 72, 42, .35);
}
.pub-fail-title { margin: 0; color: var(--brick); font-weight: 700; font-size: 13px; }
.pub-fail-detail { margin: 4px 0 0; color: var(--ink); font-size: 12.5px; line-height: 1.6; word-break: break-all; }
.pub-warnings { margin: 8px 0 0; padding-left: 18px; color: var(--brick); font-size: 12px; line-height: 1.7; }
.pub-shot { margin: 6px 0 0; color: var(--muted-soft); font-size: 11px; word-break: break-all; }
</style>
