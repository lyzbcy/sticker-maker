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
    <div class="field">
      <label>参考图库位置</label>
      <div class="dir-row">
        <input class="dir-input" :value="store.prefs.reference_lib_path || '（默认：用户数据目录/reference_library）'" readonly />
        <button class="btn-sm" @click="selectRefDir">选择文件夹</button>
        <button class="btn-sm" v-if="store.prefs.reference_lib_path" @click="store.prefs.reference_lib_path = null">重置默认</button>
      </div>
      <p class="hint">把你的参考表情放进这个文件夹，数量足够时生图会优先用它们。</p>
    </div>
  </div>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()

async function selectRefDir() {
  if (!window.api || !window.api.selectDirectory) return
  const result = await window.api.selectDirectory()
  if (!result.canceled) {
    store.prefs.reference_lib_path = result.path
  }
}
</script>
<style scoped>
.field { margin: 14px 0; }
.field.check { display: flex; align-items: center; gap: 8px; }
select { padding: 6px; border-radius: 6px; border: 1px solid #ccc; }
.dir-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.dir-input { flex: 1; padding: 6px; border: 1px solid #ccc; border-radius: 6px; color: #666; font-size: 13px; }
.btn-sm { padding: 6px 12px; border: 1px solid #4a90d9; border-radius: 6px; background: #fff; color: #4a90d9; cursor: pointer; font-size: 13px; }
.hint { color: #888; font-size: 12px; margin-top: 4px; }
</style>
