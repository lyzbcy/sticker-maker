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
.progress-bar { padding: 6px 0; }

.bar-track {
  height: 14px;
  background: var(--paper);
  border-radius: var(--r-pill);
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(30, 58, 36, .06);
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--forest), var(--sage));
  border-radius: var(--r-pill);
  transition: width .3s ease;
  box-shadow: 0 2px 6px rgba(30, 58, 36, .2);
}

.bar-info {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 13px;
  color: var(--muted);
}
.msg { font-weight: 600; color: var(--ink); }
.eta { color: var(--muted-soft); }
</style>
