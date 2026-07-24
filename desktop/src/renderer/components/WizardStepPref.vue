<template>
  <div class="step-pref">
    <p>生图偏好：</p>
    <div class="field">
      <label>默认宫格</label>
      <select v-model.number="store.prefs.grid_size">
        <option :value="4">4×4（推荐，16 张）</option>
        <option :value="3">3×3（9 张）</option>
        <option :value="2">2×2（4 张）</option>
        <option :value="1">1×1（单张）</option>
      </select>
    </div>
    <div class="field check">
      <input type="checkbox" id="transparent" v-model="store.prefs.transparent_default" />
      <label for="transparent">透明背景（prompt 模式默认抠图）</label>
    </div>
    <div class="field check">
      <input type="checkbox" id="reflib" v-model="store.prefs.ref_lib_priority" />
      <label for="reflib">参考图库数量足够时优先使用</label>
    </div>
    <div class="field check">
      <input type="checkbox" id="story" v-model="store.prefs.story_mode" />
      <label for="story">故事模式（每 4 张一个小故事，推荐）</label>
    </div>
  </div>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
</script>
<style scoped>
.field { margin: 14px 0; }
.field.check { display: flex; align-items: center; gap: 8px; }
select { padding: 6px; border-radius: 6px; border: 1px solid #ccc; }
</style>
