<template>
  <div class="featured" v-if="featured.length">
    <h4>✨ 精选表情</h4>
    <div class="grid">
      <img v-for="f in featured" :key="f.path" :src="'file://' + f.path" :alt="f.name" :title="f.name" />
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'

const featured = ref([])

onMounted(async () => {
  if (!window.api) return
  try {
    const res = await window.api.send('featured', { n: 8 })
    if (res && res.status === 'ok') {
      featured.value = res.data.sample || []
    }
  } catch (e) {
    // 静默失败（精选是锦上添花）
  }
})
</script>
<style scoped>
.featured { margin-top: 30px; }
.featured h4 { color: #666; margin-bottom: 10px; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.grid img { width: 100%; height: auto; border-radius: 6px; background: #f0f0f0; }
</style>
