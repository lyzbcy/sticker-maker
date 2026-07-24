<template>
  <div class="main">
    <header>
      <h2>表情包一键制作</h2>
      <button class="settings-btn" @click="store.phase = 'settings'">⚙ 设置</button>
    </header>
    <div class="body">
      <div v-if="!store.running && !store.lastEpisode && !store.lastError" class="idle">
        <div class="config-summary">
          <p>当前：{{ gridLabel }} / {{ store.prefs?.story_mode ? '故事模式' : '排列组合' }}</p>
          <button class="start-btn" @click="store.runGenerate">🎨 开始生图</button>
        </div>
        <div class="recent" v-if="store.episodes.length">
          <h4>最近作品</h4>
          <p v-for="ep in store.episodes.slice(0, 5)" :key="ep.path">{{ ep.name }}（{{ ep.sticker_count }} 张）</p>
        </div>
      </div>
      <div v-else-if="store.running" class="running">
        <ProgressBar />
        <button class="cancel-btn" @click="store.stopRun">取消</button>
      </div>
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
const store = useEngineStore()
const gridLabel = computed(() => {
  const g = store.prefs?.grid_size || 4
  return `${g}×${g}（${g * g} 张）`
})
onMounted(() => store.loadEpisodes())
</script>
<style scoped>
.main { padding: 24px; max-width: 720px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center; }
.settings-btn { background: none; border: 1px solid #ddd; border-radius: 6px; padding: 6px 12px; cursor: pointer; }
.idle { text-align: center; padding: 40px 0; }
.start-btn { font-size: 16px; padding: 14px 36px; margin: 20px 0; border: none; border-radius: 12px; background: #4a90d9; color: #fff; cursor: pointer; }
.start-btn:hover { background: #3a7dc9; }
.cancel-btn { margin-top: 20px; padding: 8px 20px; border: none; border-radius: 6px; background: #c33; color: #fff; cursor: pointer; }
.recent { margin-top: 30px; text-align: left; }
.recent h4 { color: #666; }
.recent p { font-size: 13px; color: #888; }
</style>
