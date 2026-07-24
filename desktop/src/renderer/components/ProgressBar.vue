<template>
  <div class="progress-bar">
    <div class="bar-track"><div class="bar-fill" :style="{ width: pct + '%' }"></div></div>
    <div class="bar-info">
      <span class="msg">{{ store.progress?.message || '处理中…' }}</span>
      <span class="eta" v-if="store.progress?.eta_seconds">剩余 ~{{ Math.ceil(store.progress.eta_seconds / 60) }} 分钟</span>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
const pct = computed(() => Math.round((store.progress?.percent || 0) * 100))
</script>
<style scoped>
.bar-track { height: 12px; background: #e0e0e0; border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, #4a90d9, #7ac67d); transition: width 0.3s; }
.bar-info { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; color: #666; }
</style>
