<template>
  <nav class="workspace-tabs" role="tablist" aria-label="工作区" data-test="workspace-tabs">
    <button v-for="item in tabs" :key="item.phase" role="tab" :aria-selected="store.phase === item.phase" :data-test="`tab-${item.phase}`" @click="store.phase = item.phase">{{ item.label }}</button>
  </nav>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
const tabs = [{ phase:'main', label:'制作表情' }, { phase:'episodes', label:'作品库' }, { phase:'allStickers', label:'全部表情' }, { phase:'health', label:'问题与警告' }]
</script>
<style scoped>
.workspace-tabs { position:sticky; top:32px; z-index:40; display:flex; gap:8px; flex-wrap:wrap; margin:32px auto 0; padding:12px 24px; max-width:1200px; background:var(--bg-cream); }
button { padding:10px 20px; border:1px solid var(--line); border-radius:14px; background:var(--card); color:var(--forest); font:inherit; cursor:pointer; }
button[aria-selected=true] { background:var(--forest); color:white; }
</style>
