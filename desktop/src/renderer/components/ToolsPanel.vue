<template>
  <div class="tools">
    <header>
      <button class="back" @click="store.phase = 'main'">← 返回</button>
      <div>
        <h2>发布与 AI 工具</h2>
        <p>把制作流程交给微信平台或你自己的 AI Agent。</p>
      </div>
    </header>

    <section class="agent-card">
      <div class="agent-copy">
        <span class="status-dot" :class="{ on: store.agentStatus.running }"></span>
        <div>
          <h3>本地 AI Agent 接口</h3>
          <p v-if="store.agentStatus.running">
            http://{{ store.agentStatus.host }}:{{ store.agentStatus.port }}
          </p>
          <p v-else>默认关闭，只监听本机 127.0.0.1。</p>
        </div>
      </div>
      <div class="agent-actions">
        <button
          v-if="!store.agentStatus.running"
          data-test="agent-start"
          class="primary"
          @click="store.startAgent"
        >启用 Agent</button>
        <button v-else class="danger" @click="store.stopAgent">停止 Agent</button>
      </div>
      <div v-if="store.agentStatus.running" class="credentials">
        <label>连接 token</label>
        <div class="copy-row">
          <code>{{ store.agentStatus.token }}</code>
          <button @click="copy(store.agentStatus.token)">复制</button>
        </div>
      </div>
      <details v-if="store.agentPrompt">
        <summary>查看给 AI Agent 的接入 prompt</summary>
        <pre>{{ store.agentPrompt }}</pre>
        <button @click="copy(store.agentPrompt)">复制 prompt</button>
      </details>
    </section>

    <section class="publish-card">
      <h3>微信表情开放平台</h3>
      <p>生成完成后可在结果页或最近作品中点击「提交微信」。首次会打开浏览器，请按页面提示登录。</p>
      <p class="notice">平台页面可能改版；若失败，日志会保留步骤，作品目录会保存现场截图。</p>
    </section>

    <LogPanel />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useEngineStore } from '../store/engine'
import LogPanel from './LogPanel.vue'
const store = useEngineStore()
onMounted(() => Promise.all([store.refreshAgent(), store.loadLogs()]))
function copy(text) {
  if (window.api?.copyText) window.api.copyText(text)
}
</script>

<style scoped>
.tools { padding: 32px; max-width: 720px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
header { display: flex; align-items: center; gap: 16px; }
header h2 { margin: 0; font: 700 22px var(--font-head); color: var(--ink); }
header p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.back { padding: 8px 18px; border: 1.5px solid var(--paper); border-radius: var(--r-pill); background: var(--card); color: var(--forest); cursor: pointer; }
.agent-card, .publish-card { padding: 24px; background: var(--card); border: 1.5px solid var(--paper); border-radius: var(--r-card); box-shadow: var(--shadow-card); }
.agent-copy { display: flex; align-items: center; gap: 12px; }
.agent-copy h3, .publish-card h3 { margin: 0 0 5px; font: 700 16px var(--font-head); color: var(--forest); }
.agent-copy p, .publish-card p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.status-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--line); box-shadow: 0 0 0 5px var(--paper); }
.status-dot.on { background: var(--correct); box-shadow: 0 0 0 5px rgba(47,125,70,.14); }
.agent-actions { margin-top: 18px; }
button { padding: 9px 16px; border: 0; border-radius: var(--r-pill); cursor: pointer; font-weight: 700; }
.primary { background: var(--forest); color: white; }
.danger { background: rgba(181,72,42,.12); color: var(--brick); }
.credentials { margin-top: 18px; }
.credentials label { display: block; margin-bottom: 6px; color: var(--muted); font-size: 12px; }
.copy-row { display: flex; gap: 8px; }
code { flex: 1; padding: 10px 12px; overflow: hidden; text-overflow: ellipsis; background: var(--bg-cream); border-radius: var(--r-sm); color: var(--forest); }
.copy-row button, details button { background: var(--sage); color: var(--forest); }
details { margin-top: 16px; color: var(--forest); }
summary { cursor: pointer; font-weight: 700; font-size: 13px; }
pre { max-height: 240px; overflow: auto; white-space: pre-wrap; padding: 14px; background: var(--bg-cream); border-radius: var(--r-md); color: var(--ink); font-size: 11px; }
.notice { margin-top: 8px !important; color: var(--brick-ink) !important; }
</style>
