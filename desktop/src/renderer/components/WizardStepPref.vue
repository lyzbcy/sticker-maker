<template>
  <div class="step-pref">
    <p class="lead">生图偏好：</p>

    <!-- 默认宫格 -->
    <div class="field">
      <label class="field-label">默认宫格</label>
      <select v-model.number="store.prefs.grid_size">
        <option :value="4">4×4（推荐，16 张）</option>
        <option :value="3">3×3（9 张）</option>
        <option :value="2">2×2（4 张）</option>
        <option :value="1">1×1（单张）</option>
      </select>
    </div>

    <!-- iOS 风格开关 -->
    <div class="field check">
      <label class="switch">
        <input type="checkbox" id="transparent" v-model="store.prefs.transparent_default" />
        <span class="slider"></span>
      </label>
      <label for="transparent" class="check-label">透明背景（prompt 模式默认抠图）</label>
    </div>
    <div class="field check">
      <label class="switch">
        <input type="checkbox" id="reflib" v-model="store.prefs.ref_lib_priority" />
        <span class="slider"></span>
      </label>
      <label for="reflib" class="check-label">参考图库数量足够时优先使用</label>
    </div>
    <div class="field check">
      <label class="switch">
        <input type="checkbox" id="story" v-model="store.prefs.story_mode" />
        <span class="slider"></span>
      </label>
      <label for="story" class="check-label">故事模式（每 4 张一个小故事，推荐）</label>
    </div>

    <!-- 参考图库位置 -->
    <div class="field">
      <label class="field-label">参考图库位置</label>
      <div class="dir-row">
        <input class="dir-input" :value="store.prefs.reference_lib_path || '（默认：用户数据目录/reference_library）'" readonly />
        <button class="btn-sm" @click="selectRefDir">选择文件夹</button>
        <button class="btn-sm btn-reset" v-if="store.prefs.reference_lib_path" @click="store.prefs.reference_lib_path = null">重置默认</button>
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
.lead { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }

.field { margin: 16px 0; }
.field.check {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-cream);
  border-radius: var(--r-md);
}
.field-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--ink);
  font-size: 14px;
}
.check-label { cursor: pointer; color: var(--ink); font-size: 14px; }

select {
  width: 100%;
  padding: 11px 16px;
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  background: var(--card);
  font-size: 14px;
  color: var(--ink);
  cursor: pointer;
  font-family: var(--font-body);
  transition: all .15s ease;
}
select:focus { outline: none; border-color: var(--sage); box-shadow: 0 0 0 4px rgba(175, 205, 168, .2); }

/* iOS 风格开关 */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 26px;
  flex-shrink: 0;
}
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--track-off);
  border-radius: var(--r-pill);
  transition: all .2s ease;
}
.slider::before {
  content: "";
  position: absolute;
  width: 20px; height: 20px;
  left: 3px; top: 3px;
  background: var(--card);
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,.15);
  transition: all .2s ease;
}
.switch input:checked + .slider { background: var(--sage); }
.switch input:checked + .slider::before { transform: translateX(18px); }

.dir-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.dir-input {
  flex: 1;
  min-width: 0;
  padding: 11px 16px;
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  background: var(--bg-cream);
  color: var(--muted);
  font-size: 13px;
  font-family: var(--font-body);
}
.btn-sm {
  padding: 10px 18px;
  border: 1.5px solid var(--forest);
  border-radius: var(--r-pill);
  background: var(--card);
  color: var(--forest);
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  transition: all .15s ease;
}
.btn-sm:hover { background: var(--forest); color: var(--white); transform: translateY(-1px); }
.btn-reset { border-color: var(--line); color: var(--muted); }
.btn-reset:hover { background: var(--paper); color: var(--ink); }

.hint { color: var(--muted-soft); font-size: 12px; margin-top: 6px; }
</style>
