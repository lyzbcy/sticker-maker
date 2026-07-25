<template>
  <div class="step-mode">
    <p class="lead">设置不同人数表情包的出现概率（<strong>建议单人</strong>，实测效果最好）：</p>
    <div class="sliders">
      <div v-for="(label, key) in labels" :key="key" class="slider-row">
        <label>{{ label }}</label>
        <input type="range" min="0" max="100" :value="Math.round(modeProbs[key] * 100)"
               @input="update(key, $event)" />
        <span class="pct">{{ Math.round(modeProbs[key] * 100) }}%</span>
      </div>
    </div>
    <p class="sum" :class="{ bad: !sumOk }">总和：{{ sum }}%（需 = 100%）</p>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
const labels = { single: '单人', duo: '双人', trio: '三人', quad: '四人' }
if (!store.prefs) store.prefs = { mode_probs: { single: 0.5, duo: 0.3, trio: 0, quad: 0.2 } }
if (!store.prefs.mode_probs) store.prefs.mode_probs = { single: 0.5, duo: 0.3, trio: 0, quad: 0.2 }
const modeProbs = computed(() => store.prefs.mode_probs)
const sum = computed(() => Math.round((modeProbs.value.single + modeProbs.value.duo + modeProbs.value.trio + modeProbs.value.quad) * 100))
const sumOk = computed(() => sum.value === 100)
function update(key, ev) {
  store.prefs.mode_probs[key] = parseInt(ev.target.value) / 100
}
</script>
<style scoped>
.lead { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.lead strong { color: var(--forest); }

.sliders { display: flex; flex-direction: column; gap: 6px; }

.slider-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: var(--bg-cream);
  border-radius: var(--r-md);
}
.slider-row label {
  width: 56px;
  font-weight: 600;
  color: var(--ink);
  font-size: 14px;
}
.slider-row input { flex: 1; accent-color: var(--forest); cursor: pointer; }

.pct {
  min-width: 48px;
  text-align: center;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: var(--candy-yellow);
  color: var(--ink);
  font-size: 12px;
  font-weight: 700;
}

.sum {
  margin-top: 18px;
  padding: 10px 16px;
  border-radius: var(--r-md);
  background: rgba(175, 205, 168, .3);
  color: var(--forest);
  font-weight: 700;
  font-size: 14px;
  text-align: center;
}
.sum.bad {
  background: rgba(181, 72, 42, .12);
  color: var(--brick);
}
</style>
