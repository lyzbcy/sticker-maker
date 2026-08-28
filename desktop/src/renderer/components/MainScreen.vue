<template>
  <div class="main">
    <header>
      <h2 class="title">表情包一键制作</h2>
      <div class="icon-group">
        <button class="icon-btn" title="发布与 AI 工具" @click="store.phase = 'tools'">
          <span class="icon">↗</span>
        </button>
        <button class="icon-btn" title="设置" @click="store.phase = 'settings'">
          <span class="icon">⚙</span>
        </button>
        <button class="icon-btn" title="关于" @click="store.phase = 'about'">
          <span class="icon">i</span>
        </button>
      </div>
    </header>

    <div class="body">
      <!-- 空闲态 -->
      <div v-if="!store.running && !store.lastEpisode && !store.lastError" class="idle">
        <!-- 主操作：紧凑 hero -->
        <div class="hero-compact">
          <div class="hero-copy">
            <h3 class="hero-title">🎨 表情包一键制作</h3>
            <p class="config-summary">
              <strong>{{ gridLabel }}</strong> · {{ store.prefs?.story_mode ? '故事模式' : '排列组合' }}
              · 主角色 <strong>{{ topChars }}</strong>
              <template v-if="defaultSeries"> · 自动命名「{{ defaultSeries }} {{ defaultSeriesNext }}」</template>
            </p>
            <button class="start-btn" @click="store.runGenerate">
              开始生图
            </button>
          </div>
        </div>

        <!-- 最近作品（高频信息前置） -->
        <div class="recent" v-if="store.episodes.length">
          <div class="recent-head">
            <h4 class="block-title">最近作品</h4>
            <button class="view-all" @click="store.phase = 'episodes'">全部作品（{{ store.episodes.length }}）→</button>
          </div>
          <div class="recent-grid">
            <div class="sticker-card" v-for="ep in store.episodes.slice(0, 6)" :key="ep.path"
                 @click="ep.complete && store.openEpisode(ep.path)">
              <div class="sticker-dot" :class="{ done: ep.published }"></div>
              <div class="sticker-text">
                <p class="sticker-name">{{ ep.album_name || ep.name }}</p>
                <p class="sticker-meta">
                  {{ ep.sticker_count }} 张<template v-if="ep.published"> · 已发布</template>
                </p>
              </div>
              <button class="mini-publish" v-if="ep.complete" :disabled="store.publishing"
                      @click.stop="store.publishEpisode(ep.path)">
                提交
              </button>
            </div>
          </div>
        </div>
        <!-- 空态：还没做过作品，用自家表情打个招呼（润物细无声） -->
        <div class="recent" v-else>
          <div class="recent-head">
            <h4 class="block-title">最近作品</h4>
          </div>
          <p class="empty-hint">还没有作品——点上面的「开始生图」，几分钟后就有一整套表情啦 ✨</p>
        </div>

        <FeaturedShowcase />
      </div>

      <!-- 运行态 -->
      <div v-else-if="store.running" class="running">
        <ProgressBar />
        <p class="running-hint">底部状态栏实时显示当前在做什么、在等什么 📍</p>
        <button class="cancel-btn" @click="store.stopRun">取消</button>
      </div>

      <!-- 结果态 -->
      <div v-else>
        <ResultPreview />
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted } from 'vue'
import { useEngineStore } from '../store/engine'
import ProgressBar from './ProgressBar.vue'
import ResultPreview from './ResultPreview.vue'
import FeaturedShowcase from './FeaturedShowcase.vue'
const store = useEngineStore()
const gridLabel = computed(() => {
  const g = store.prefs?.grid_size || 4
  return `${g}×${g}（${g * g} 张）`
})
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
onMounted(() => {
  store.loadEpisodes()
  store.loadSeries()
})
</script>
<style scoped>
.main { padding: 32px; max-width: 720px; margin: 0 auto; }

header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }

.title {
  margin: 0;
  font-family: var(--font-head);
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}

.icon-group { display: flex; gap: 10px; }

.icon-btn {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: 50%;
  cursor: pointer;
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.icon-btn:hover {
  transform: translateY(-2px);
  border-color: var(--sage);
  box-shadow: var(--shadow-card);
}
.icon {
  font-weight: 700;
  color: var(--forest);
  font-size: 16px;
  line-height: 1;
}

.idle { display: flex; flex-direction: column; gap: 28px; }

/* ============ 紧凑 hero（主操作区） ============ */
.hero-compact {
  padding: 26px 28px;
  border-radius: var(--r-card);
  background: var(--hero-gradient);
  box-shadow: var(--shadow-card);
}
.hero-copy { position: relative; z-index: 2; }
.hero-title {
  margin: 0 0 8px;
  font-family: var(--font-head);
  font-size: 22px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--ink);
}

.config-summary {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 13px;
}
.config-summary strong { color: var(--forest); font-weight: 700; }

/* 胶囊主按钮（森林绿） */
.start-btn {
  font-family: var(--font-head);
  font-size: 16px;
  font-weight: 700;
  padding: 14px 36px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--forest);
  color: var(--white);
  cursor: pointer;
  box-shadow: var(--shadow-btn);
  transition: all .15s ease;
}
.start-btn:hover { background: var(--forest-hover); transform: translateY(-1px); }
.start-btn:active { transform: translateY(1px); }

/* ============ 最近作品 sticker-card 网格 ============ */
.recent { display: flex; flex-direction: column; gap: 12px; }
.empty-hint { margin: 0; color: var(--muted); font-size: 13px; padding: 10px 2px; }

.recent-head { display: flex; align-items: baseline; justify-content: space-between; }
.view-all {
  background: none; border: none; color: var(--forest); font-size: 12.5px;
  font-weight: 700; cursor: pointer; padding: 2px 4px;
}
.view-all:hover { text-decoration: underline; }

.block-title {
  margin: 0;
  font-family: var(--font-head);
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  opacity: .7;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.sticker-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
  cursor: pointer;
}
.mini-publish {
  margin-left: auto;
  padding: 7px 12px;
  border: 1px solid var(--sage);
  border-radius: var(--r-pill);
  background: var(--card);
  color: var(--forest);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}
.mini-publish:hover:not(:disabled) { background: var(--sage); }
.mini-publish:disabled { opacity: .5; cursor: wait; }
.sticker-card:hover {
  transform: translateY(-2px);
  border-color: var(--sage);
  box-shadow: var(--shadow-card);
}
.sticker-dot {
  flex-shrink: 0;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--sage);
  box-shadow: 0 0 0 4px rgba(175, 205, 168, .25);
}
.sticker-dot.done { background: var(--correct); box-shadow: 0 0 0 4px rgba(47, 125, 70, .2); }
.sticker-text { min-width: 0; }
.sticker-name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sticker-meta { margin: 2px 0 0; font-size: 12px; color: var(--muted-soft); }

/* ============ 运行态 ============ */
.running { padding: 12px 0; }
.running-hint {
  margin: 14px 0 0;
  font-size: 13px;
  color: var(--muted-soft);
  text-align: center;
}
.cancel-btn {
  margin-top: 20px;
  padding: 10px 24px;
  border: 1.5px solid var(--brick);
  border-radius: var(--r-pill);
  background: var(--card);
  color: var(--brick);
  font-weight: 600;
  cursor: pointer;
  transition: all .15s ease;
}
.cancel-btn:hover { background: var(--brick); color: var(--white); transform: translateY(-1px); }
</style>
