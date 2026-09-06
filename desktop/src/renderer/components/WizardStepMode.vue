<template>
  <div class="step-mode">
    <p class="lead">每次生成几张一组的表情（<strong>建议单人</strong>，实测效果最好）。不用凑满 100%，保存时自动折算：</p>
    <div class="presets">
      <span class="presets-label">快捷设置：</span>
      <button class="preset-btn" @click="preset(1, 0, 0, 0)">只生成单人</button>
      <button class="preset-btn" @click="preset(0.5, 0.5, 0, 0)">单人+双人</button>
      <button class="preset-btn" @click="preset(0.5, 0.3, 0, 0.2)">经典搭配</button>
      <button class="preset-btn" @click="preset(0.25, 0.25, 0.25, 0.25)">四种均分</button>
    </div>
    <div class="sliders">
      <div v-for="(label, key) in labels" :key="key" class="slider-row">
        <label>{{ label }}</label>
        <input type="range" min="0" max="100" step="5" :value="pct(key)"
               @input="setPct(key, $event.target.value)" />
        <input type="number" min="0" max="100" step="5" :value="pct(key)"
               class="num" @change="setPct(key, $event.target.value)" />
        <span class="pct-sign">%</span>
      </div>
    </div>
    <p class="sum-hint">总和 {{ sum }}% —— 不是 100% 也没关系，保存时自动按比例折算</p>
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
const pct = (key) => Math.round((Number(modeProbs.value[key]) || 0) * 100)
const sum = computed(() => ['single', 'duo', 'trio', 'quad'].reduce((t, k) => t + pct(k), 0))
function setPct(key, v) {
  store.prefs.mode_probs[key] = Math.max(0, Math.min(100, parseInt(v) || 0)) / 100
}
function preset(s, d, t, q) {
  store.prefs.mode_probs = { single: s, duo: d, trio: t, quad: q }
}
</script>
<style scoped>
.lead { margin: 0 0 14px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.lead strong { color: var(--forest); }
.presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.presets-label { font-size: 12.5px; color: var(--muted); font-weight: 600; }
.preset-btn { padding: 6px 13px; border: 1.5px solid var(--forest, #2e4a34); background: white;
  color: var(--forest, #2e4a34); border-radius: 999px; cursor: pointer; font-size: 12.5px; font-weight: 700; }
.preset-btn:hover { background: var(--forest, #2e4a34); color: white; }
.sliders { display: flex; flex-direction: column; gap: 6px; }
.slider-row { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  background: var(--bg-cream); border-radius: var(--r-md); }
.slider-row label { width: 56px; font-weight: 600; color: var(--ink); font-size: 14px; }
.slider-row input[type="range"] { flex: 1; accent-color: var(--forest); cursor: pointer; }
.slider-row .num { width: 58px; padding: 5px 6px; border: 1px solid var(--line, #ddd);
  border-radius: 8px; font-size: 13px; text-align: center; }
.pct-sign { color: var(--muted); font-size: 12px; }
.sum-hint { margin-top: 14px; font-size: 12px; color: var(--muted, #888); }
</style>
