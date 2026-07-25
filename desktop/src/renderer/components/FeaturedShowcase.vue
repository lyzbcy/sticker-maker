<template>
  <div class="featured" v-if="featured.length">
    <h4 class="block-title">✨ 精选表情</h4>
    <div class="grid">
      <div class="grid-item" v-for="f in featured" :key="f.path">
        <img :src="fileUrl(f.path)" :alt="f.name" :title="f.name" />
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'

const featured = ref([])
const fileUrl = (path) => window.api?.toFileUrl ? window.api.toFileUrl(path) : `file://${path}`

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
.featured { display: flex; flex-direction: column; gap: 12px; }

.block-title {
  margin: 0;
  font-family: var(--font-head);
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  opacity: .7;
}

.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.grid-item {
  overflow: hidden;
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.grid-item:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-card-hover);
}
.grid-item img {
  display: block;
  width: 100%;
  height: auto;
}
</style>
