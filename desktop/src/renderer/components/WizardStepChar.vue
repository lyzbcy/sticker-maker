<template>
  <div class="step-char">
    <p class="lead">每个角色的出场概率（生成时抽谁做主角）。不用凑满 100%，保存时自动按比例折算：</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="sliders">
      <div v-for="(_, name) in store.characters" :key="name" class="slider-row">
        <span class="char-badge">{{ name.charAt(0) }}</span>
        <label :title="name">{{ name }}</label>
        <input type="range" min="0" max="100" step="5" :value="pct(name)"
               @input="setPct(name, $event.target.value)" />
        <input type="number" min="0" max="100" step="5" :value="pct(name)"
               class="num" @change="setPct(name, $event.target.value)" />
        <span class="pct-sign">%</span>
      </div>
    </div>
    <div class="tools" v-if="Object.keys(store.characters).length > 1">
      <button class="tool-btn" @click="evenAll">⚖️ 所有角色均分</button>
      <span class="sum-hint">总和 {{ sum }}% —— 不是 100% 也没关系，保存时自动折算</span>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
if (store.prefs && !store.prefs.single_char_probs) store.prefs.single_char_probs = {}
const charProbs = computed(() => store.prefs.single_char_probs || {})
const names = computed(() => Object.keys(store.characters))
const pct = (name) => Math.round((Number(charProbs.value[name]) || 0) * 100)
const sum = computed(() => names.value.reduce(
  (t, name) => t + pct(name), 0))
function setPct(name, v) {
  const n = Math.max(0, Math.min(100, parseInt(v) || 0))
  store.prefs.single_char_probs[name] = n / 100
}
function evenAll() {
  const equal = 1 / names.value.length
  names.value.forEach(name => { store.prefs.single_char_probs[name] = equal })
}
</script>
<style scoped>
.lead { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.loading { padding: 20px; text-align: center; color: var(--muted-soft); font-size: 14px; }
.sliders { display: flex; flex-direction: column; gap: 6px; }
.slider-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; background: var(--bg-cream); border-radius: var(--r-md);
}
.char-badge { flex-shrink: 0; width: 28px; height: 28px; display: grid; place-items: center;
  border-radius: 50%; background: rgba(175, 205, 168, .4); color: var(--forest);
  font-weight: 700; font-size: 13px; }
.slider-row label { width: 72px; font-weight: 600; color: var(--ink); font-size: 14px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slider-row input[type="range"] { flex: 1; accent-color: var(--forest); cursor: pointer; }
.slider-row .num { width: 58px; padding: 5px 6px; border: 1px solid var(--line, #ddd);
  border-radius: 8px; font-size: 13px; text-align: center; }
.pct-sign { color: var(--muted); font-size: 12px; }
.tools { margin-top: 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.tool-btn { padding: 7px 14px; border: 1.5px solid var(--forest, #2e4a34); background: white;
  color: var(--forest, #2e4a34); border-radius: 999px; cursor: pointer; font-size: 12.5px; font-weight: 700; }
.tool-btn:hover { background: var(--forest, #2e4a34); color: white; }
.sum-hint { font-size: 12px; color: var(--muted, #888); }
</style>
