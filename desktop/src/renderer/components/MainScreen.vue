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
      <!-- 空闲态：Hero + 操作 -->
      <div v-if="!store.running && !store.lastEpisode && !store.lastError" class="idle">
        <div class="hero-card">
          <div class="hero-ring"></div>
          <div class="hero-ring ring-2"></div>
          <div class="hero-copy">
            <span class="eyebrow">✨ 今天想做点啥</span>
            <h3 class="hero-title">把你脑洞里的<br/><em>小表情</em>，全做出来</h3>
            <p class="config-summary">
              当前：<strong>{{ gridLabel }}</strong> · {{ store.prefs?.story_mode ? '故事模式' : '排列组合' }}
            </p>
            <button class="start-btn" @click="store.runGenerate">
              🎨 开始生图
            </button>
          </div>
        </div>

        <!-- 最近作品 -->
        <div class="recent" v-if="store.episodes.length">
          <h4 class="block-title">最近作品</h4>
          <div class="recent-grid">
            <div class="sticker-card" v-for="ep in store.episodes.slice(0, 5)" :key="ep.path">
              <div class="sticker-dot"></div>
              <div class="sticker-text">
                <p class="sticker-name">{{ ep.name }}</p>
                <p class="sticker-meta">{{ ep.sticker_count }} 张</p>
              </div>
              <button class="mini-publish" :disabled="store.publishing" @click="store.publishEpisode(ep.path)">
                提交微信
              </button>
            </div>
          </div>
        </div>

        <FeaturedShowcase />
      </div>

      <!-- 运行态 -->
      <div v-else-if="store.running" class="running">
        <ProgressBar />
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
onMounted(() => store.loadEpisodes())
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

/* ============ Hero 卡片（三色斜渐变 + 装饰圆环） ============ */
.hero-card {
  position: relative;
  overflow: hidden;
  padding: 40px 32px;
  border-radius: var(--r-card);
  background: var(--hero-gradient);
  box-shadow: var(--shadow-card);
}
.hero-ring {
  position: absolute;
  width: 280px; height: 280px;
  border: 1.5px solid rgba(255, 255, 255, .8);
  border-radius: 50%;
  right: -80px; top: -90px;
  pointer-events: none;
}
.hero-ring.ring-2 {
  width: 180px; height: 180px;
  right: -30px; top: -30px;
  border-color: rgba(255, 255, 255, .6);
}
.hero-copy { position: relative; z-index: 2; }

.eyebrow {
  display: inline-block;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, .68);
  color: var(--forest);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 14px;
}

.hero-title {
  margin: 0 0 10px;
  font-family: var(--font-head);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--ink);
}
.hero-title em { color: var(--forest); font-style: normal; }

.config-summary {
  margin: 8px 0 22px;
  color: var(--muted);
  font-size: 14px;
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
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
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
