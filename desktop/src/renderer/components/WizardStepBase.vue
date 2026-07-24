<template>
  <div class="step-base">
    <p>软件内置了 4 个角色和 base 图，按概率随机选用。你也可以上传自己的 base 图，或用 AI 生成新的。</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="char-grid">
      <div v-for="(info, name) in store.characters" :key="name" class="char-card">
        <h4>{{ name }}</h4>
        <p>{{ Object.keys(info.bases).length }} 张 base 图</p>
      </div>
    </div>

    <div class="custom-section">
      <h4>自定义 base 图</h4>

      <!-- 上传 base -->
      <div class="action-row">
        <button class="btn" @click="uploadBase" :disabled="uploading">
          {{ uploading ? '处理中…' : '📤 上传 base 图' }}
        </button>
        <span class="hint" v-if="uploadedPath">已选：{{ uploadedName }}</span>
      </div>

      <!-- AI 生成 base -->
      <div class="action-row">
        <input class="prompt-input" v-model="aiPrompt" placeholder="描述你想要的角色（如：粉色头发的小女孩）" />
        <button class="btn" @click="generateBase" :disabled="generating || !aiPrompt">
          {{ generating ? '生成中（约1分钟）…' : '✨ AI 生成 base' }}
        </button>
      </div>
      <p class="hint" v-if="generateMsg" :class="{ err: generateErr }">{{ generateMsg }}</p>

      <p class="hint note">提示：自定义 base 图会作为新角色加入，可在大本营「设置」里调整概率。</p>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useEngineStore } from '../store/engine'

const store = useEngineStore()
const uploading = ref(false)
const uploadedPath = ref('')
const uploadedName = ref('')
const aiPrompt = ref('')
const generating = ref(false)
const generateMsg = ref('')
const generateErr = ref(false)

onMounted(() => store.loadCharacters())

async function uploadBase() {
  if (!window.api || !window.api.selectFile) return
  uploading.value = true
  try {
    const result = await window.api.selectFile()
    if (result.canceled) {
      uploading.value = false
      return
    }
    uploadedPath.value = result.path
    uploadedName.value = result.path.split('/').pop()
    // 上传后调 add_base（复制到用户 base 目录）
    const res = await window.api.send('add_base', { path: result.path, name: uploadedName.value })
    if (res && res.status === 'ok') {
      generateMsg.value = '✅ base 图已添加'
      generateErr.value = false
      store.loadCharacters()   // 刷新列表
    } else {
      generateMsg.value = '❌ 添加失败：' + (res && res.error || '未知错误')
      generateErr.value = true
    }
  } catch (e) {
    generateMsg.value = '❌ 上传失败：' + (e.message || e)
    generateErr.value = true
  } finally {
    uploading.value = false
  }
}

async function generateBase() {
  if (!aiPrompt.value || !window.api) return
  generating.value = true
  generateMsg.value = ''
  try {
    const res = await window.api.send('generate_base', { prompt: aiPrompt.value })
    if (res && res.status === 'ok' && res.data && res.data.path) {
      generateMsg.value = '✅ AI 已生成 base 图：' + res.data.path.split('/').pop()
      generateErr.value = false
      store.loadCharacters()
    } else {
      generateMsg.value = '❌ 生成失败' + (res && res.errors ? '：' + res.errors[0].message : '')
      generateErr.value = true
    }
  } catch (e) {
    generateMsg.value = '❌ 生成失败：' + (e.message || e)
    generateErr.value = true
  } finally {
    generating.value = false
  }
}
</script>
<style scoped>
.char-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 16px 0; }
.char-card { background: #f6f8fa; padding: 12px; border-radius: 8px; text-align: center; }
.char-card h4 { margin: 0 0 4px; }
.custom-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid #eee; }
.custom-section h4 { margin: 0 0 12px; }
.action-row { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
.prompt-input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 6px; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; background: #4a90d9; color: #fff; cursor: pointer; white-space: nowrap; }
.btn:disabled { background: #ccc; cursor: not-allowed; }
.hint { color: #888; font-size: 13px; }
.hint.err { color: #c33; }
.note { margin-top: 12px; font-style: italic; }
</style>
