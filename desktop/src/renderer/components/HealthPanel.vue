<template>
  <section class="health-panel" data-test="health-panel">
    <header><h2>问题与警告</h2><button :disabled="checking" @click="refresh">{{ checking ? '检查中…' : '重新检查' }}</button></header>
    <p>这里说明未就绪的功能及影响，你可以随时返回制作、浏览和评分。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <article>
      <h3>{{ !store.codexStatus ? '生图环境检查中…' : store.codexStatus.image_ready ? '生图环境已就绪' : '生图环境需要处理' }}</h3>
      <p>{{ store.codexStatus?.guidance_msg || 'Codex 用于生成新图片；未配置时仍可浏览、评分和导出已有作品。' }}</p>
      <button @click="showCodex = !showCodex">{{ showCodex ? '收起处理步骤' : '快速处理生图环境' }}</button>
      <WizardStepCodex v-if="showCodex" @skip-check="showCodex = false" />
    </article>
    <article>
      <h3>{{ browser.ready ? `发布浏览器已就绪：${browser.name}` : '发布浏览器未就绪' }}</h3>
      <p>发布和同步状态需要浏览器。优先使用本机 Edge/Chrome；没有时可安装独立组件。浏览、评分和导出不受影响。</p>
      <button :disabled="installing" @click="installBrowser">{{ installing ? '正在安装…' : browser.ready ? '安装备用浏览器组件' : '安装浏览器组件' }}</button>
    </article>
    <article>
      <h3>{{ credentials.configured ? '发布账号已配置' : '发布账号未配置' }}</h3>
      <p>未配置时无法登录微信平台同步或投稿，不影响本地制作。</p>
      <button @click="settings('publish')">处理发布账号</button>
    </article>
    <article>
      <h3>{{ library.offline ? '资源库离线' : library.connected ? '资源库已连接' : '尚未连接共享资源' }}</h3>
      <p>换电脑后选择原资源位置即可找回作品；离线时请等待共享目录同步完成。</p>
      <button @click="settings('resource')">选择或检查资源位置</button>
    </article>
    <article>
      <h3>日志与排障</h3>
      <p>关键操作先进入内存，每5秒或累计64 KB批量写入本机应用目录；错误与正常退出时尽快写出。保留7天，最多20 MB，不放进共享工程。</p>
      <label><input data-test="debug-mode" type="checkbox" :checked="diagnostics.debug" @change="setDebug($event.target.checked)" />开启详细排障日志</label>
      <p>排障模式记录更多步骤与诊断上下文，写入前脱敏。排查结束后可关闭。</p>
      <p v-if="diagnostics.error" role="alert">{{ diagnostics.error }}</p>
      <button @click="exportLogs">导出完整诊断日志</button>
      <button @click="store.phase = 'feedback'">反馈问题</button>
      <p v-if="message" role="status">{{ message }}</p>
    </article>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useEngineStore } from '../store/engine'
import WizardStepCodex from './WizardStepCodex.vue'
const store = useEngineStore()
const browser=ref({}), library=ref({}), credentials=ref({}), diagnostics=ref({}), checking=ref(false), installing=ref(false), showCodex=ref(false), error=ref(''), message=ref('')
function settings(tab) { store.settingsTab=tab; store.phase='settings' }
async function command(cmd) { const result=await window.api?.send(cmd, {}); if(result?.status!=='ok') throw Error(result?.errors?.[0]?.message || '检查失败'); return result.data || {} }
async function refresh() {
  if(checking.value) return
  checking.value=true; error.value=''
  const checks=await Promise.allSettled([store.checkCodex(), command('browser_runtime_status'),command('publish_credentials_status'),command('library_status'),window.api?.diagnosticSnapshot?.()])
  for (const [index, target] of [[1,browser],[2,credentials],[3,library],[4,diagnostics]]) {
    const result=checks[index]; if(result.status==='fulfilled') target.value=result.value || {}; else error.value += `${result.reason?.message || '检查失败'}；`
  }
  checking.value=false
}
async function installBrowser() {
  installing.value=true; error.value=''
  try { await command('install_chromium'); browser.value=await command('browser_runtime_status') }
  catch(e) { error.value=e.message }
  finally { installing.value=false }
}
async function setDebug(value) {
  try { diagnostics.value=await window.api?.diagnosticMode(value) || {}; message.value=value?'已开启详细排障日志':'已关闭详细排障日志' }
  catch(e) { error.value=e.message }
}
async function exportLogs() { try { const result=await window.api?.exportDiagnostics(); if(result?.ok) message.value='已导出脱敏日志' } catch(e) { error.value=e.message } }
onMounted(refresh)
</script>
<style scoped>
.health-panel { max-width:900px; margin:24px auto 90px; padding:0 24px; } header { display:flex; align-items:center; justify-content:space-between; }
article { margin:18px 0; padding:20px; border:1px solid var(--line); background:var(--card); border-radius:18px; } h3 { margin:0 0 12px; } p { line-height:1.7; overflow-wrap:anywhere; }
button { padding:9px 16px; border:1px solid var(--line); border-radius:12px; background:var(--card); color:var(--forest); font:inherit; margin:4px; cursor:pointer; } button:disabled { opacity:.5; }
</style>
