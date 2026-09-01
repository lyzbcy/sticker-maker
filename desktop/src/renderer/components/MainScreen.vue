<template>
  <div class="main">
    <!-- ============ 顶栏：品牌 + 导航 ============ -->
    <header class="topbar">
      <div class="brand">
        <div class="brand-logo">🐟</div>
        <h1 class="brand-name">表情包一键制作</h1>
      </div>
      <nav class="nav-group">
        <button class="nav-btn" title="发布与 AI 工具" @click="store.phase = 'tools'">
          <span class="nav-ico">↗</span>发布与AI工具
        </button>
        <button class="nav-btn" title="设置" @click="store.phase = 'settings'">
          <span class="nav-ico">⚙</span>设置
        </button>
        <button class="nav-btn" title="关于" @click="store.phase = 'about'">
          <span class="nav-ico">i</span>关于
        </button>
      </nav>
    </header>

    <!-- ============ 空闲态 ============ -->
    <div v-if="!store.running && !store.lastEpisode && !store.lastError" class="idle">
      <!-- 主操作：渐变 hero（左文案 + 右「贴纸拼图」预览装饰） -->
      <section class="hero">
        <span class="blob blob-1"></span>
        <span class="blob blob-2"></span>

        <div class="hero-copy">
          <p class="hero-eyebrow">👋 {{ greeting }}，今天也来撸点表情</p>
          <h2 class="hero-title">一键生成你的<span class="hl">专属表情包</span></h2>

          <!-- 配置摘要：胶囊标签（宫格 · 模式 · 主角色 · 系列） -->
          <div class="pill-row">
            <span class="pill">
              <span class="pill-label">宫格</span>
              <span class="pill-val">{{ gridLabel }}</span>
            </span>
            <span class="pill">
              <span class="pill-label">模式</span>
              <span class="pill-val">{{ modeLabel }}</span>
            </span>
            <span class="pill" :title="topChars">
              <span class="pill-label">主角色</span>
              <span class="pill-val">{{ topChars }}</span>
            </span>
            <span class="pill" v-if="defaultSeries" :title="`自动命名「${defaultSeries} ${defaultSeriesNext}」`">
              <span class="pill-label">系列</span>
              <span class="pill-val">「{{ defaultSeries }} {{ defaultSeriesNext }}」自动命名</span>
            </span>
          </div>

          <div class="cta-row">
            <button class="start-btn" @click="store.runGenerate">
              <span class="start-emoji">🎨</span>开始生图
            </button>
            <div class="batch-box">
              <label class="batch-label">
                批量
                <select v-model="batchCount" class="batch-select">
                  <option v-for="n in [2,3,5,10,20]" :key="n" :value="n">{{ n }} 组</option>
                </select>
              </label>
              <label class="batch-check">
                <input type="checkbox" v-model="batchAutoPublish" />
                完成后自动发布
              </label>
              <button class="batch-btn" :disabled="store.running" @click="startBatch">
                {{ store.running ? '运行中…' : '🚀 批量生成' }}
              </button>
            </div>
            <p class="cta-hint">点一下就好 ✨ 单组几分钟；批量时每组完成后自动命名并提交（需在设置里配好默认系列）</p>
          </div>
          <p v-if="store.batchInfo" class="batch-summary">
            上次批量：生成 {{ store.batchInfo.generated_ok }}/{{ store.batchInfo.requested }} 组，
            发布 {{ store.batchInfo.published_ok }} 组
          </p>
        </div>

        <!-- 贴纸拼图预览：纯 CSS，呼应本次宫格配置 -->
        <div class="hero-side">
          <div class="sheet-wrap">
            <div class="sheet-back"></div>
            <div class="sheet">
              <div class="sheet-grid" :style="{ '--g': gridSize }">
                <div v-for="n in gridSize * gridSize" :key="n" class="sheet-cell"
                     :class="n % 5 === 1 ? 'candy c' + (n % 3) : ''">
                  <span v-if="n % 5 === 1">{{ faceAt(n) }}</span>
                </div>
              </div>
              <span class="sheet-tape"></span>
            </div>
          </div>
          <p class="sheet-caption">生成后自动切好 {{ gridSize * gridSize }} 张小表情 ✂️</p>
        </div>
      </section>

      <!-- 最近作品（高频信息前置） -->
      <section class="recent">
        <div class="section-head">
          <h3 class="section-title">🎨 最近作品</h3>
          <span class="count-chip">共 {{ store.episodes.length }} 个</span>
          <button class="view-all" @click="store.phase = 'episodes'">
            全部作品（{{ store.episodes.length }}）<span class="arrow">→</span>
          </button>
        </div>

        <div class="recent-grid" v-if="store.episodes.length">
          <article v-for="ep in recentEpisodes" :key="ep.path" class="sticker-card"
                   :class="{ incomplete: !ep.complete }"
                   @click="ep.complete && store.openEpisode(ep.path)">
            <div class="thumb-wrap">
              <img v-if="ep.cover" class="thumb" :src="fileUrl(ep.cover)" alt="" @error="onThumbError" />
              <div v-else class="thumb thumb-empty">🧸</div>
              <span v-if="ep.published" class="pub-badge">✓ 已发布</span>
            </div>
            <div class="card-text">
              <p class="card-name">{{ ep.album_name || ep.name }}</p>
              <p class="card-meta">
                {{ ep.sticker_count }} 张<template v-if="epDate(ep)"> · {{ epDate(ep) }}</template>
                <span v-if="!ep.complete" class="tag-incomplete">未完成</span>
              </p>
            </div>
            <button class="mini-publish" v-if="ep.complete" :disabled="store.publishing"
                    @click.stop="store.publishEpisode(ep.path)">
              {{ ep.published ? '再次提交' : '提交' }}
            </button>
          </article>
        </div>

        <!-- 空态：还没做过作品，用自家表情打个招呼（润物细无声） -->
        <div v-else class="empty-box">
          <span class="empty-emoji">🧺</span>
          <p class="empty-hint">还没有作品——点上面的「开始生图」，几分钟后就有一整套表情啦 ✨</p>
        </div>
      </section>

      <!-- 自家精选表情（既是装饰又是实力展示） -->
      <section class="showcase-card">
        <FeaturedShowcase />
      </section>
    </div>

    <!-- ============ 运行态 ============ -->
    <div v-else-if="store.running" class="running">
      <div class="running-card">
        <div class="working-dots"><span></span><span></span><span></span></div>
        <h3 class="running-title">小画家正在努力画图中…</h3>
        <ProgressBar />
        <p class="running-hint">底部状态栏实时显示当前在做什么、在等什么 📍</p>
        <button class="cancel-btn" @click="store.stopRun">取消生成</button>
      </div>
    </div>

    <!-- ============ 结果态 ============ -->
    <div v-else class="result-area">
      <ResultPreview />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useEngineStore } from '../store/engine'
import ProgressBar from './ProgressBar.vue'
import ResultPreview from './ResultPreview.vue'
import FeaturedShowcase from './FeaturedShowcase.vue'

const store = useEngineStore()

// 批量生成（组数 + 完成后自动发布）
const batchCount = ref(5)
const batchAutoPublish = ref(true)
function startBatch() {
  if (store.running) return
  store.runBatch(batchCount.value, batchAutoPublish.value)
}

const gridSize = computed(() => Number(store.prefs?.grid_size) || 4)
const gridLabel = computed(() => `${gridSize.value}×${gridSize.value} · ${gridSize.value * gridSize.value} 张`)
const modeLabel = computed(() => (store.prefs?.story_mode ? '故事模式' : '排列组合'))

// 主角色摘要：概率前两名
const topChars = computed(() => {
  const probs = store.prefs?.single_char_probs || {}
  return Object.entries(probs)
    .filter(([, v]) => Number(v) > 0)
    .sort((a, b) => b[1] - a[1]).slice(0, 2)
    .map(([name, v]) => `${name} ${Math.round(v * 100)}%`).join(' / ') || '未配置'
})

// 默认系列（run 自动命名）
const defaultSeries = computed(() => {
  const sid = store.prefs?.default_series_id
  if (!sid) return ''
  const s = (store.seriesList || []).find(x => x.id === sid)
  return s ? s.name : ''
})
const defaultSeriesNext = computed(() => {
  const sid = store.prefs?.default_series_id
  if (!sid) return ''
  const s = (store.seriesList || []).find(x => x.id === sid)
  return s ? s.next_number : ''
})

// 按时间问候，多一点"人味"
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深啦'
  if (h < 12) return '早上好呀'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const recentEpisodes = computed(() => store.episodes.slice(0, 6))
const faces = ['😆', '🥰', '😮', '😢', '🤔', '😎']
const faceAt = (n) => faces[Math.floor(n / 5) % faces.length]

const epDate = (ep) => (ep.created_at || '').slice(0, 10)
const fileUrl = (path) => window.api?.toFileUrl ? window.api.toFileUrl(path) : `file://${path}`
const onThumbError = (e) => { e.target.style.display = 'none' }

onMounted(() => {
  store.loadEpisodes()
  store.loadSeries()
})
</script>

<style scoped>
.main { padding: 26px 32px 40px; max-width: 980px; margin: 0 auto; }

/* ============ 顶栏 ============ */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 22px;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand-logo {
  width: 40px; height: 40px;
  display: grid; place-items: center;
  background: var(--forest);
  border-radius: var(--r-md);
  font-size: 20px;
  transform: rotate(-6deg);
  box-shadow: var(--shadow-soft);
}
.brand-name {
  margin: 0;
  font-family: var(--font-head);
  font-size: 19px;
  font-weight: 700;
  color: var(--ink);
}
.nav-group { display: flex; gap: 10px; }
.nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  cursor: pointer;
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.nav-btn:hover {
  transform: translateY(-2px);
  border-color: var(--sage);
  box-shadow: var(--shadow-card);
}
.nav-ico {
  font-weight: 700;
  color: var(--forest);
  font-size: 13px;
  line-height: 1;
}

/* ============ 空闲态布局 ============ */
.idle { display: flex; flex-direction: column; gap: 26px; }

/* ---- 渐变 hero（主操作区） ---- */
.hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 36px;
  padding: 34px 36px;
  border-radius: var(--r-card);
  background: var(--hero-gradient);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
/* 奶油纸面点纹 */
.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(30, 58, 36, .05) 1.1px, transparent 1.1px);
  background-size: 20px 20px;
  pointer-events: none;
}
/* 漂浮糖果色泡泡（很慢很轻） */
.blob { position: absolute; border-radius: 50%; pointer-events: none; }
.blob-1 {
  width: 190px; height: 190px;
  background: rgba(183, 229, 255, .38);
  top: -70px; right: -50px;
  animation: floatSoft 9s ease-in-out infinite alternate;
}
.blob-2 {
  width: 140px; height: 140px;
  background: rgba(183, 255, 213, .32);
  bottom: -60px; left: 26%;
  animation: floatSoft 7s ease-in-out 1.2s infinite alternate-reverse;
}
@keyframes floatSoft {
  from { transform: translateY(0); }
  to   { transform: translateY(-14px); }
}

.hero-copy { position: relative; z-index: 1; flex: 1; min-width: 0; }
.hero-eyebrow {
  margin: 0 0 6px;
  font-family: var(--font-head);
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
.hero-title {
  margin: 0 0 16px;
  font-family: var(--font-fun);
  font-size: 32px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--ink);
}
/* 手帐荧光笔高亮 */
.hl {
  background: linear-gradient(180deg, transparent 60%, var(--marker) 60%);
  padding: 0 3px;
  border-radius: 2px;
}

/* 配置摘要胶囊 */
.pill-row { display: flex; flex-wrap: wrap; gap: 8px; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: 100%;
  padding: 7px 14px;
  background: rgba(255, 255, 255, .88);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-soft);
}
.pill-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted-soft);
}
.pill-val {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--forest);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

/* 主按钮（大热区胶囊） */
.cta-row { margin-top: 20px; }
.batch-box { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.batch-label { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 4px; }
.batch-select { border: 1px solid #ddd; border-radius: 8px; padding: 6px 8px; font-size: 13px; }
.batch-check { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 4px; cursor: pointer; }
.batch-btn { border: 0; background: var(--brick, #b5482a); color: white; border-radius: 999px;
  padding: 10px 18px; font-weight: 800; cursor: pointer; }
.batch-btn:hover:not(:disabled) { filter: brightness(1.1); }
.batch-btn:disabled { opacity: .6; cursor: wait; }
.batch-summary { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
.start-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-head);
  font-size: 17px;
  font-weight: 700;
  padding: 16px 44px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--forest);
  color: var(--white);
  cursor: pointer;
  box-shadow: var(--shadow-btn);
  transition: all .15s ease;
}
.start-btn:hover {
  background: var(--forest-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}
.start-btn:active { transform: translateY(1px); }
.start-emoji {
  font-size: 19px;
  line-height: 1;
  transition: transform .2s ease;
}
.start-btn:hover .start-emoji { transform: rotate(-10deg) scale(1.15); }
.cta-hint {
  margin: 10px 2px 0;
  color: var(--muted-soft);
  font-size: 12px;
}

/* ---- 贴纸拼图预览（纯 CSS 装饰，呼应宫格配置） ---- */
.hero-side {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.sheet-wrap { position: relative; width: 250px; }
.sheet-back {
  position: absolute;
  inset: 0;
  background: var(--paper);
  border-radius: var(--r-lg);
  transform: rotate(-5deg) translate(-8px, 7px);
}
.sheet {
  position: relative;
  z-index: 1;
  padding: 14px;
  background: var(--card);
  border: 2px dashed var(--line);
  border-radius: var(--r-lg);
  transform: rotate(3deg);
  box-shadow: var(--shadow-soft);
  transition: transform .25s ease;
}
.sheet:hover { transform: rotate(0deg) scale(1.03); }
/* 和纸胶带 */
.sheet-tape {
  position: absolute;
  top: -11px;
  left: 50%;
  width: 86px;
  height: 22px;
  background: rgba(245, 224, 138, .8);
  border-radius: 3px;
  transform: translateX(-50%) rotate(-2deg);
  box-shadow: var(--shadow-soft);
}
.sheet-grid {
  display: grid;
  grid-template-columns: repeat(var(--g), 1fr);
  gap: 8px;
}
.sheet-cell {
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  background: var(--bg-cream);
  border-radius: var(--r-sm);
  font-size: clamp(12px, 3.2vw, 20px);
  user-select: none;
}
.sheet-cell.c0 { background: var(--candy-pink); }
.sheet-cell.c1 { background: var(--candy-blue); }
.sheet-cell.c2 { background: var(--candy-yellow); }
.sheet-caption {
  margin: 16px 0 0;
  width: max-content;
  max-width: 100%;
  padding: 6px 14px;
  background: rgba(255, 255, 255, .88);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-soft);
  font-size: 12px;
  color: var(--muted);
}

/* ============ 区块通用标题 ============ */
.section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.section-title {
  margin: 0;
  font-family: var(--font-head);
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
}
.count-chip {
  padding: 3px 10px;
  background: var(--paper);
  border-radius: var(--r-pill);
  font-size: 11.5px;
  font-weight: 700;
  color: var(--muted-soft);
}
.view-all {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  color: var(--forest);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.view-all:hover {
  border-color: var(--sage);
  transform: translateX(2px);
}
.view-all .arrow { transition: transform .15s ease; }
.view-all:hover .arrow { transform: translateX(2px); }

/* ============ 最近作品卡片 ============ */
.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
}
.sticker-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 14px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-soft);
  cursor: pointer;
  transition: all .15s ease;
}
.sticker-card:hover {
  transform: translateY(-3px) rotate(-.6deg);
  border-color: var(--sage);
  box-shadow: var(--shadow-card);
}
.sticker-card.incomplete { opacity: .62; cursor: default; }
.sticker-card.incomplete:hover {
  transform: none;
  border-color: var(--paper);
  box-shadow: var(--shadow-soft);
}
.thumb-wrap { position: relative; flex-shrink: 0; }
.thumb {
  width: 46px; height: 46px;
  border-radius: var(--r-sm);
  object-fit: cover;
  background: var(--bg-cream);
  display: grid;
  place-items: center;
  box-shadow: var(--shadow-soft);
}
.thumb-empty { font-size: 22px; }
.pub-badge {
  position: absolute;
  top: -7px; left: -8px;
  padding: 2px 8px;
  background: var(--correct);
  color: var(--white);
  font-size: 10px;
  font-weight: 700;
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-soft);
  white-space: nowrap;
}
.card-text { min-width: 0; flex: 1; }
.card-name {
  margin: 0;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--muted-soft);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.tag-incomplete {
  padding: 1px 8px;
  background: var(--paper);
  border-radius: var(--r-pill);
  font-size: 10.5px;
  font-weight: 700;
  color: var(--muted-soft);
}
.mini-publish {
  flex-shrink: 0;
  margin-left: auto;
  padding: 7px 13px;
  border: 1.5px solid var(--sage);
  border-radius: var(--r-pill);
  background: var(--card);
  color: var(--correct);
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  transition: all .15s ease;
}
.mini-publish:hover:not(:disabled) { background: var(--sage); color: var(--forest); }
.mini-publish:disabled { opacity: .5; cursor: wait; }

/* 空态提示 */
.empty-box {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 24px 26px;
  border: 2px dashed var(--line);
  border-radius: var(--r-lg);
  background: rgba(255, 255, 255, .6);
}
.empty-emoji { font-size: 30px; line-height: 1; }
.empty-hint { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.7; }

/* ============ 精选表情（自家表情展示位） ============ */
.showcase-card {
  padding: 16px 20px 18px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-card);
  box-shadow: var(--shadow-soft);
}
/* 8 张排成一长条更"表情墙"，窄窗口退回 4 列 */
.showcase-card :deep(.grid) { grid-template-columns: repeat(8, 1fr); gap: 8px; }
.showcase-card :deep(.block-title) { opacity: 1; }

/* ============ 运行态 ============ */
.running { display: flex; justify-content: center; padding: 44px 0; }
.running-card {
  width: 100%;
  max-width: 560px;
  padding: 30px 32px;
  text-align: center;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-card);
  box-shadow: var(--shadow-card);
}
.working-dots {
  display: inline-flex;
  gap: 6px;
  margin-bottom: 10px;
}
.working-dots span {
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--sage);
  animation: dotBounce 1s ease-in-out infinite;
}
.working-dots span:nth-child(2) { animation-delay: .15s; background: var(--marker); }
.working-dots span:nth-child(3) { animation-delay: .3s; background: var(--sky); }
@keyframes dotBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.running-title {
  margin: 0 0 18px;
  font-family: var(--font-fun);
  font-size: 21px;
  font-weight: 700;
  color: var(--forest);
}
.running-hint {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: var(--muted-soft);
}
.cancel-btn {
  margin-top: 20px;
  padding: 10px 26px;
  border: 1.5px solid var(--brick);
  border-radius: var(--r-pill);
  background: var(--card);
  color: var(--brick);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s ease;
}
.cancel-btn:hover { background: var(--brick); color: var(--white); transform: translateY(-1px); }

/* ============ 结果态 ============ */
.result-area { max-width: 720px; margin: 0 auto; padding-top: 16px; }

/* ============ 响应窗口宽度（Electron 最小约 900px） ============ */
@media (max-width: 880px) {
  .hero { padding: 26px 24px; }
  .hero-side { display: none; }
  .hero-title { font-size: 26px; }
  .recent-grid { grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); }
  .showcase-card :deep(.grid) { grid-template-columns: repeat(4, 1fr); }
  .nav-btn { padding: 8px 12px; }
}
</style>
