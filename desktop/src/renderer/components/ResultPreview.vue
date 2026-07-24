<template>
  <div class="result">
    <div v-if="store.lastError" class="error-box">
      <h4>❌ 生成失败</h4>
      <p v-for="(e, i) in store.lastError" :key="i">{{ e.message || e.gate }}</p>
      <button class="btn" @click="store.runGenerate">重试</button>
    </div>
    <div v-else-if="store.lastEpisode" class="success">
      <h4>✅ 完成！{{ store.lastEpisode.stickers }} 张表情</h4>
      <p class="hint">目录：{{ store.lastEpisode.episode_dir }}</p>
      <div class="actions">
        <button class="btn" @click="openFinder">在 Finder 中显示</button>
        <button class="btn btn-green" @click="store.runGenerate">再生成一组</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
async function openFinder() {
  if (store.lastEpisode?.episode_dir && window.api) {
    await window.api.send('open_in_finder', { path: store.lastEpisode.episode_dir })
  }
}
</script>
<style scoped>
.error-box { background: #fff0f0; padding: 16px; border-radius: 8px; color: #c33; }
.success { background: #f0fff4; padding: 16px; border-radius: 8px; }
.actions { display: flex; gap: 10px; margin-top: 12px; }
.btn { padding: 6px 14px; border: none; border-radius: 6px; background: #4a90d9; color: #fff; cursor: pointer; }
.btn-green { background: #7ac67d; }
.hint { color: #888; font-size: 12px; word-break: break-all; }
</style>
