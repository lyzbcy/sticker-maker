<template>
  <div class="step-base">
    <p>软件内置了 4 个角色和 base 图，按概率随机选用。</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="char-grid">
      <div v-for="(info, name) in store.characters" :key="name" class="char-card">
        <h4>{{ name }}</h4>
        <p>{{ Object.keys(info.bases).length }} 张 base 图</p>
      </div>
    </div>
    <p class="hint">（上传 / AI 生成 base 的完整能力在后续版本，当前先用内置角色）</p>
  </div>
</template>
<script setup>
import { onMounted } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
onMounted(() => store.loadCharacters())
</script>
<style scoped>
.char-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 16px 0; }
.char-card { background: #f6f8fa; padding: 12px; border-radius: 8px; text-align: center; }
.char-card h4 { margin: 0 0 4px; }
.hint { color: #888; font-size: 13px; }
</style>
