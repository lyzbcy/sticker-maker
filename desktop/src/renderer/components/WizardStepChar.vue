<template>
  <div class="step-char">
    <p>单人模式下，各角色被选为 base 的概率：</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="sliders">
      <div v-for="(_, name) in store.characters" :key="name" class="slider-row">
        <label>{{ name }}</label>
        <input type="range" min="0" max="100" :value="Math.round((charProbs[name] || 0) * 100)"
               @input="update(name, $event)" />
        <span class="pct">{{ Math.round((charProbs[name] || 0) * 100) }}%</span>
      </div>
    </div>
    <p class="hint">总和无需固定，系统会自动归一化。</p>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
if (store.prefs && !store.prefs.single_char_probs) store.prefs.single_char_probs = {}
const charProbs = computed(() => store.prefs.single_char_probs || {})
function update(name, ev) {
  store.prefs.single_char_probs[name] = parseInt(ev.target.value) / 100
}
</script>
<style scoped>
.slider-row { display: flex; align-items: center; gap: 12px; margin: 10px 0; }
.slider-row label { width: 80px; }
.slider-row input { flex: 1; }
.pct { width: 40px; text-align: right; }
.hint { color: #888; font-size: 13px; }
</style>
