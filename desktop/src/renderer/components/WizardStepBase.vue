<template>
  <div class="step-base">
    <p class="lead">软件内置了 4 个角色和 base 图，按概率随机选用。你也可以上传自己的 base 图，或用 AI 生成新的。</p>
    <div v-if="Object.keys(store.characters).length === 0" class="loading">加载中…</div>
    <div v-else class="char-grid">
      <div v-for="(info, name) in store.characters" :key="name" class="char-card">
        <div class="char-avatar">{{ name.charAt(0) }}</div>
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
        <button class="btn btn-ai" @click="generateBase" :disabled="generating || !aiPrompt">
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
.lead { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }

.loading { padding: 20px; text-align: center; color: var(--muted-soft); font-size: 14px; }

/* 角色卡片网格（大圆角 + hover 抬升） */
.char-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin: 16px 0 24px;
}
.char-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 14px;
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-soft);
  text-align: center;
  transition: all .15s ease;
}
.char-card:hover {
  transform: translateY(-3px);
  border-color: var(--sage);
  box-shadow: var(--shadow-card);
}
.char-avatar {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(175, 205, 168, .35);
  color: var(--forest);
  font-family: var(--font-head);
  font-weight: 700;
  font-size: 18px;
  margin-bottom: 4px;
}
.char-card h4 { margin: 0; font-family: var(--font-head); font-size: 15px; color: var(--ink); }
.char-card p { margin: 0; font-size: 12px; color: var(--muted-soft); }

/* 自定义区 */
.custom-section {
  margin-top: 8px;
  padding-top: 22px;
  border-top: 1.5px dashed var(--paper);
}
.custom-section h4 {
  margin: 0 0 14px;
  font-family: var(--font-head);
  font-size: 15px;
  color: var(--ink);
}

.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
}

.prompt-input {
  flex: 1;
  padding: 11px 16px;
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  background: var(--bg-cream);
  font-size: 14px;
  color: var(--ink);
  transition: all .15s ease;
  font-family: var(--font-body);
}
.prompt-input::placeholder { color: var(--muted-faint); }
.prompt-input:focus {
  outline: none;
  border-color: var(--sage);
  background: var(--card);
  box-shadow: 0 0 0 4px rgba(175, 205, 168, .2);
}

.btn {
  padding: 11px 22px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--forest);
  color: var(--white);
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s ease;
  box-shadow: var(--shadow-btn);
}
.btn:hover:not(:disabled) { background: var(--forest-hover); transform: translateY(-1px); }
.btn:active:not(:disabled) { transform: translateY(1px); }
.btn:disabled { background: var(--paper); color: var(--muted-faint); cursor: not-allowed; box-shadow: none; }

.btn-ai {
  background: linear-gradient(135deg, var(--forest), var(--correct));
}

.hint { color: var(--muted-soft); font-size: 13px; }
.hint.err { color: var(--brick); font-weight: 600; }
.note { margin-top: 14px; font-style: italic; }
</style>
