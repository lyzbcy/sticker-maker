<template>
  <section class="feedback">
    <button @click="$emit('back')">← 返回主页</button>
    <h2>遇到问题反馈</h2>
    <p>写下你遇到了什么、希望怎么改。发送后直接交给作者，不需要跳转。</p>
    <p class="response" role="status" aria-live="polite" v-show="result">{{ result }}</p>
    <label>问题类型 <select v-model="category"><option>使用问题</option><option>生成失败</option><option>安装或更新</option><option>功能建议</option></select></label>
    <label class="message">你的留言<textarea v-model="message" maxlength="1500" rows="5" placeholder="例如：点开始后出现了什么提示？请不要填写密码或登录令牌。"></textarea></label>
    <label><input type="checkbox" v-model="includeLogs" /> 附上最近的诊断日志（可取消）</label>
    <p class="hint">发送前会移除常见令牌、账号与本机路径；不读取作品、密码或登录文件。请检查留言是否含私人信息。</p>
    <p class="hint">反馈附带下方预览中的诊断摘要，按发送大小限制，不再固定截取30条。完整日志可导出，关闭软件后也会保留。</p>
    <details v-if="includeLogs"><summary>预览将发送的日志</summary><pre>{{ preview }}</pre></details>
    <button @click="refreshDiagnostics" :disabled="busy">刷新诊断摘要</button>
    <button @click="exportLogs" :disabled="busy">导出完整诊断日志</button>
    <button :disabled="busy || !message.trim()" @click="send">{{ busy ? '发送中…' : '发送给作者' }}</button>
    <button @click="copy" :disabled="busy">复制诊断信息</button>
  </section>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useEngineStore } from '../store/engine'
import { scrubText } from '../../shared/diagnostics'
defineEmits(['back'])
const store = useEngineStore()
const message = ref(''), category = ref('使用问题'), includeLogs = ref(true), busy = ref(false), result = ref('')
const persisted = ref(null)
function tailBytes(text, budget) {
  const lines = Array.from(text), selected = []; let bytes = 0
  for (let i=lines.length-1;i>=0;i--) { const n=new TextEncoder().encode(lines[i]).length; if(bytes+n>budget) break; selected.push(lines[i]); bytes+=n }
  return selected.reverse().join('')
}
const preview = computed(() => {
  const text = scrubText(persisted.value ?? store.activity.map(a => `[${a.stage}] ${a.message}`).join('\n'))
  const budget = Math.max(0, 8400-new TextEncoder().encode(`${category.value}\n${scrubText(message.value)}`).length)
  return tailBytes(text, budget)
})
async function refreshDiagnostics() {
  if (!window.api?.diagnosticSnapshot) return
  try { const data=await window.api.diagnosticSnapshot(); persisted.value=data.text; if(data.error) result.value=data.error }
  catch { result.value='读取本地日志失败，可复制当前活动记录。' }
}
onMounted(refreshDiagnostics)
async function exportLogs() {
  try { const data=await window.api?.exportDiagnostics(); if(data?.ok) result.value='已导出脱敏日志，可检查后提供给作者。' }
  catch { result.value='导出失败，请检查保存目录权限。' }
}
async function send() {
  if (busy.value || !message.value.trim()) return
  busy.value = true; result.value = ''
  try {
    const res = await window.api?.sendFeedback({ message: message.value, category: category.value, logs: includeLogs.value ? preview.value : '' })
    result.value = res?.ok ? '已送达作者，谢谢你的反馈！' : `发送未完成：${res?.error || '请从桌面软件打开此页面'}。可以复制诊断信息后联系作者，或稍后重试。`
    if (res?.ok) message.value = ''
  } catch (e) { result.value = `发送未完成：${e.message}，请稍后重试。` }
  finally { busy.value = false }
}
async function copy() {
  if (busy.value) return
  busy.value = true; result.value = ''
  try {
    const text = [category.value, message.value]
    if (includeLogs.value) text.push(preview.value)
    const res = await window.api?.copyText(scrubText(text.join('\n')))
    result.value = res?.ok ? '已复制，可粘贴给作者。' : '复制未完成，请从桌面软件打开。'
  } catch {
    result.value = '复制未完成，请稍后重试；留言已保留。'
  } finally { busy.value = false }
}
</script>
<style scoped>
.feedback{max-width:720px;margin:32px auto;padding:24px;background:var(--paper);border-radius:22px;color:var(--ink)}
.response{padding:12px;border:1px solid var(--sage);border-radius:12px;background:var(--bg-cream);font-weight:600}
label{display:block;margin:16px 0}.message textarea{display:block;width:100%;margin-top:8px;resize:vertical}button,textarea,select{font:inherit;padding:10px 14px;border:1px solid var(--sage);border-radius:12px;background:var(--bg-cream);color:var(--forest)}button{cursor:pointer;margin-right:8px}button:disabled{opacity:.5;cursor:default}.hint{font-size:12px;color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;font-size:12px}
</style>
