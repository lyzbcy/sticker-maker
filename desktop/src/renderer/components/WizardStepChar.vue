<template>
  <div class="step-char">
    <p class="lead">单人模式下，各角色被选为 base 的概率：</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="sliders">
      <div v-for="(_, name) in store.characters" :key="name" class="slider-row">
        <span class="char-badge">{{ name.charAt(0) }}</span>
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
.lead { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.loading { padding: 20px; text-align: center; color: var(--muted-soft); font-size: 14px; }

.sliders { display: flex; flex-direction: column; gap: 6px; }

.slider-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-cream);
  border-radius: var(--r-md);
}
.char-badge {
  flex-shrink: 0;
  width: 28px; height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(175, 205, 168, .4);
  color: var(--forest);
  font-weight: 700;
  font-size: 13px;
}
.slider-row label {
  width: 70px;
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

.hint { margin-top: 16px; color: var(--muted-soft); font-size: 13px; }
</style>
