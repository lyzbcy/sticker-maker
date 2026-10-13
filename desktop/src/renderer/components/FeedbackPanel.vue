<template>
  <section class="feedback">
    <button @click="$emit('back')">← 返回主页</button>
    <h2>遇到问题反馈</h2>
    <p>写下你遇到了什么、希望怎么改。发送后直接交给作者，不需要跳转。</p>
    <label>问题类型 <select v-model="category"><option>使用问题</option><option>生成失败</option><option>安装或更新</option><option>功能建议</option></select></label>
    <label class="message">你的留言<textarea v-model="message" maxlength="1500" rows="6" placeholder="例如：点开始后出现了什么提示？请不要填写密码或登录令牌。"></textarea></label>
    <label><input type="checkbox" v-model="includeLogs" /> 附上最近的诊断日志（可取消）</label>
    <p class="hint">发送前会移除常见令牌、账号与本机路径；不读取作品、密码或登录文件。请检查留言是否含私人信息。</p>
    <details v-if="includeLogs"><summary>预览将发送的日志</summary><pre>{{ preview }}</pre></details>
    <button :disabled="busy || !message.trim()" @click="send">{{ busy ? '发送中…' : '发送给作者' }}</button>
    <button @click="copy" :disabled="busy">复制诊断信息</button>
    <p role="status">{{ result }}</p>
  </section>
</template>
<script setup>
import { ref, computed } from 'vue'
import { useEngineStore } from '../store/engine'
import { scrubText } from '../../shared/diagnostics'
defineEmits(['back'])
const store = useEngineStore()
const message = ref(''), category = ref('使用问题'), includeLogs = ref(true), busy = ref(false), result = ref('')
const preview = computed(() => scrubText(store.activity.slice(-30).map(a => `[${a.stage}] ${a.message}`).join('\n')).slice(-1800))
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
  const res = await window.api?.copyText(scrubText(`${category.value}\n${message.value}\n${preview.value}`))
  result.value = res?.ok ? '已复制，可粘贴给作者。' : '复制未完成，请从桌面软件打开。'
}
</script>
<style scoped>
.feedback{max-width:720px;margin:32px auto;padding:24px;background:var(--paper);border-radius:22px;color:var(--ink)}
label{display:block;margin:16px 0}.message textarea{display:block;width:100%;margin-top:8px;resize:vertical}button,textarea,select{font:inherit;padding:10px 14px;border:1px solid var(--sage);border-radius:12px;background:var(--bg-cream);color:var(--forest)}button{cursor:pointer;margin-right:8px}button:disabled{opacity:.5;cursor:default}.hint{font-size:12px;color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;font-size:12px}
</style>
