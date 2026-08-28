<template>
  <div class="status-bar" :class="{ running: store.running, error: hasError }">
    <!-- 展开的日志面板 -->
    <div v-if="expanded" class="activity-panel">
      <div class="panel-head">
        <span>实时活动（做什么 · 输入 · 输出 · 在等什么）</span>
        <button class="clear-btn" @click="store.activity = []">清空</button>
      </div>
      <div class="activity-list" ref="listEl">
        <div v-if="!store.activity.length" class="empty">暂无记录</div>
        <div v-for="(a, i) in store.activity" :key="i" class="activity-row" :class="rowClass(a)">
          <span class="t">{{ fmtTime(a.t) }}</span>
          <span class="stage">{{ a.stage || '·' }}</span>
          <span class="msg">{{ a.message }}</span>
        </div>
      </div>
    </div>

    <!-- 常驻底栏 -->
    <div class="bar" @click="expanded = !expanded">
      <span class="dot" :class="dotClass"></span>
      <span class="status-text">{{ statusText }}</span>
      <span class="elapsed" v-if="store.running && elapsed">{{ elapsed }}</span>
      <span class="expand">{{ expanded ? '收起 ▾' : '日志 ▴' }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useEngineStore } from '../store/engine'

const store = useEngineStore()
const expanded = ref(false)
const listEl = ref(null)
const nowTick = ref(Date.now())
let timer = null

onMounted(() => { timer = setInterval(() => { nowTick.value = Date.now() }, 1000) })
onUnmounted(() => clearInterval(timer))

const hasError = computed(() => !store.running && !!store.lastError?.length)

const dotClass = computed(() => {
  if (store.running) return 'run'
  if (hasError.value) return 'err'
  return 'ok'
})

const lastMessage = computed(() => {
  const list = store.activity
  return list.length ? list[list.length - 1].message : ''
})

const statusText = computed(() => {
  if (store.running) return lastMessage.value || '运行中…'
  if (hasError.value) return store.lastError?.[0]?.message || '出错了'
  if (store.lastEpisode) return `上次任务完成 · ${store.lastEpisode.stickers ?? 0} 张`
  return lastMessage.value || '就绪 · 引擎待命'
})

const elapsed = computed(() => {
  if (!store.runStartedAt) return ''
  const secs = Math.max(0, Math.floor((nowTick.value - store.runStartedAt) / 1000))
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `已用时 ${m}:${String(s).padStart(2, '0')}`
})

function fmtTime(t) {
  const d = new Date(t || Date.now())
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, '0')).join(':')
}

function rowClass(a) {
  if (/失败|超时|错误/.test(a.message || '')) return 'bad'
  if (/输出就绪|完成/.test(a.message || '')) return 'good'
  return ''
}

// 新日志到达时自动滚到底部（仅展开时）
watch(() => store.activity.length, async () => {
  if (expanded.value && listEl.value) {
    await Promise.resolve()
    listEl.value.scrollTop = listEl.value.scrollHeight
  }
})
</script>

<style scoped>
.status-bar {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  z-index: 50;
  font-size: 13px;
}

/* ===== 常驻底栏 ===== */
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  background: var(--forest);
  color: rgba(255, 255, 255, .92);
  cursor: pointer;
  user-select: none;
  box-shadow: 0 -4px 16px rgba(30, 58, 36, .18);
}
.error .bar { background: #7a2f1d; }

.dot {
  flex-shrink: 0;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--sage);
}
.dot.run { background: #7fd8ff; animation: pulse 1.2s ease infinite; }
.dot.err { background: #ff9d7a; }
.dot.ok { background: var(--sage); }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(127, 216, 255, .5); }
  50% { box-shadow: 0 0 0 5px rgba(127, 216, 255, 0); }
}

.status-text {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
}

.elapsed {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  opacity: .75;
  font-size: 12px;
}

.expand {
  flex-shrink: 0;
  font-size: 12px;
  opacity: .65;
  padding: 3px 10px;
  border-radius: var(--r-pill);
  border: 1px solid rgba(255, 255, 255, .25);
}

/* ===== 展开面板 ===== */
.activity-panel {
  background: var(--card);
  border-top: 1.5px solid var(--paper);
  box-shadow: 0 -8px 24px rgba(30, 58, 36, .12);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 18px;
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  border-bottom: 1px solid var(--paper);
}
.clear-btn {
  border: none;
  background: transparent;
  color: var(--muted-soft);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: var(--r-pill);
}
.clear-btn:hover { background: var(--paper); color: var(--ink); }

.activity-list {
  max-height: 220px;
  overflow-y: auto;
  padding: 8px 18px 10px;
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
  line-height: 1.8;
}
.empty { color: var(--muted-faint); padding: 8px 0; }

.activity-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.activity-row .t { color: var(--muted-faint); flex-shrink: 0; font-size: 11px; }
.activity-row .stage {
  flex-shrink: 0;
  min-width: 30px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--forest);
  background: rgba(175, 205, 168, .35);
  border-radius: 4px;
  padding: 1px 5px;
}
.activity-row .msg {
  color: var(--ink);
  word-break: break-all;
}
.activity-row.bad .msg { color: var(--brick); }
.activity-row.good .msg { color: var(--correct); }
</style>
