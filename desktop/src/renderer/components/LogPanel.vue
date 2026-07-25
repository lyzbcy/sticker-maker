<template>
  <section class="logs-card">
    <div class="section-head">
      <div>
        <h3>运行日志</h3>
        <p>仅保留内存中的最近 50 条，关闭软件后自动消失。</p>
      </div>
      <div class="actions">
        <button @click="copyLogs">复制</button>
        <button @click="store.clearLogs">清空</button>
      </div>
    </div>
    <div v-if="store.logs.length" class="log-list">
      <div v-for="(entry, index) in store.logs" :key="`${entry.time}-${index}`" class="log-row">
        <span class="time">{{ entry.time?.slice(11) }}</span>
        <span class="level" :class="entry.level">{{ entry.level }}</span>
        <span class="message">{{ entry.message }}</span>
      </div>
    </div>
    <p v-else class="empty">暂无日志。</p>
  </section>
</template>

<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
function copyLogs() {
  const text = store.logs.map(item =>
    `${item.time || ''} [${item.level || 'info'}] ${item.message || ''}`,
  ).join('\n')
  if (window.api?.copyText) window.api.copyText(text)
}
</script>

<style scoped>
.logs-card { padding: 22px; background: var(--card); border: 1.5px solid var(--paper); border-radius: var(--r-card); box-shadow: var(--shadow-card); }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
h3 { margin: 0 0 4px; color: var(--forest); font-family: var(--font-head); font-size: 16px; }
p { margin: 0; color: var(--muted); font-size: 12px; }
.actions { display: flex; gap: 8px; }
button { padding: 7px 13px; border: 1px solid var(--line); border-radius: var(--r-pill); background: var(--bg-cream); color: var(--forest); cursor: pointer; }
.log-list { margin-top: 14px; max-height: 250px; overflow: auto; border-top: 1px dashed var(--line); }
.log-row { display: grid; grid-template-columns: 66px 52px 1fr; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--paper); font-size: 12px; }
.time { color: var(--muted-soft); font-variant-numeric: tabular-nums; }
.level { color: var(--correct); text-transform: uppercase; font-weight: 700; }
.level.error { color: var(--brick); }
.message { color: var(--ink); word-break: break-word; }
.empty { padding-top: 16px; text-align: center; }
</style>
