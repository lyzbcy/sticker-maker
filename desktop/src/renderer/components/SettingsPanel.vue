<template>
  <div class="settings">
    <header>
      <button class="back" @click="back">← 返回</button>
      <h2>设置</h2>
    </header>

    <!-- 顶部 tab：一个主题一屏，不再长条滚动 -->
    <div class="tab-bar">
      <button class="tab" :class="{ active: tab === 'gen' }" @click="tab = 'gen'">🎨 生图设置</button>
      <button class="tab" :class="{ active: tab === 'prompts' }" @click="switchPrompts">📝 Prompt 方案</button>
      <button class="tab" :class="{ active: tab === 'publish' }" @click="switchPublish">
        📤 发布账号
        <span v-if="credStatus.configured" class="tab-dot ok" title="已配置"></span>
        <span v-else class="tab-dot warn" title="未配置，提交微信前需要填写"></span>
      </button>
    </div>

    <!-- Prompt 方案：多套可切换，评分数据可反哺 AI 来调这里 -->
    <div v-if="tab === 'prompts'" class="settings-body">
      <div class="section">
        <h3>生图 Prompt 方案</h3>
        <p class="hint" style="margin-bottom:12px;">
          每套方案 = 风格块（STYLE）+ 各模式附加指令。生成时按「默认方案」套用；
          把作品详情页的评分文件（rating.json）发给 AI，AI 就能按打分反向优化这里的方案。
        </p>
        <div class="ps-list">
          <div v-for="s in promptSets" :key="s.id" class="ps-item"
               :class="{ active: s.id === activePromptSet }" @click="editSet(s)">
            <div class="ps-head">
              <span class="ps-name">{{ s.name }}</span>
              <span v-if="s.id === activePromptSet" class="ps-badge">使用中</span>
              <span v-if="s.id.startsWith('builtin')" class="ps-badge dim">内置</span>
            </div>
            <p class="ps-meta">{{ (s.style_block || '').slice(0, 80) }}…</p>
            <div class="ps-ops" @click.stop>
              <button v-if="!s.id.startsWith('builtin')" class="ps-btn danger" @click="deleteSet(s)">删除</button>
              <button class="ps-btn" @click="dupSet(s)">复制</button>
              <button v-if="s.id !== activePromptSet" class="ps-btn primary" @click="setDefault(s)">设为默认</button>
            </div>
          </div>
          <button class="ps-item add" @click="newSet">＋ 新建方案</button>
        </div>
      </div>
      <div class="section" v-if="editing">
        <h3>编辑：{{ editing.name || '新方案' }}</h3>
        <div class="field">
          <label class="field-label">方案名</label>
          <input class="dir-input" v-model="editing.name" placeholder="例如：黏土风·实验" />
        </div>
        <div class="field">
          <label class="field-label">风格块 STYLE（替换内置萌系规格；留空=用内置）</label>
          <textarea class="ps-editor" v-model="editing.style_block" rows="8"
                    placeholder="STYLE (strictly identical across all panels):&#10;- ..."></textarea>
        </div>
        <div class="field">
          <label class="field-label">排列组合模式附加指令（追加在模板末尾）</label>
          <textarea class="ps-editor" v-model="editing.combo_extra" rows="3"></textarea>
        </div>
        <div class="field">
          <label class="field-label">故事模式附加指令</label>
          <textarea class="ps-editor" v-model="editing.story_extra" rows="2"></textarea>
        </div>
        <div class="field">
          <label class="field-label">参考图模式附加指令</label>
          <textarea class="ps-editor" v-model="editing.ref_extra" rows="2"></textarea>
        </div>
        <div class="row-actions">
          <button class="save" @click="saveSet">保存方案</button>
          <button class="save" v-if="!editing.id || editing.id.startsWith('builtin')"
                  @click="saveSet(true)">另存为新方案并设为默认</button>
        </div>
        <p v-if="psSavedTip" class="hint">{{ psSavedTip }}</p>
      </div>
    </div>

    <!-- 生图设置 -->
    <div v-if="tab === 'gen'" class="settings-body">
      <div class="section">
        <h3 class="section-title">生图偏好</h3>
        <WizardStepPref />
      </div>
      <div class="section">
        <h3 class="section-title">角色概率</h3>
        <WizardStepChar />
      </div>
      <div class="section">
        <h3 class="section-title">模式概率</h3>
        <WizardStepMode />
      </div>
      <div class="section">
        <h3 class="section-title">base 图管理</h3>
        <WizardStepBase />
      </div>
      <div v-if="store.lastError" class="settings-error">
        {{ store.lastError[0]?.message }}
      </div>
      <button class="save" @click="save">保存生图设置</button>
    </div>

    <!-- 发布账号 -->
    <div v-else class="settings-body">
      <div class="section">
        <h3 class="section-title">微信表情开放平台账号</h3>
        <p class="pub-account-hint">
          「一键提交微信」时自动登录用。账号密码安全保存在
          {{ isWindows ? 'Windows 凭据管理器' : '系统钥匙串' }}，不上传、不落明文。
          登录态失效时软件会自动用这里的账号密码重新登录。
        </p>
        <div class="pub-account-form">
          <div class="field">
            <label class="field-label">账号（邮箱地址）</label>
            <input v-model="pubAccount" type="text" class="pub-input"
                   :placeholder="credStatus.configured ? credStatus.account : '输入账号（邮箱）'" />
          </div>
          <div class="field">
            <label class="field-label">密码</label>
            <input v-model="pubPassword" type="password" class="pub-input"
                   :placeholder="credStatus.configured ? '已保存（输入新密码可覆盖）' : '输入密码'" />
          </div>
          <div class="pub-account-actions">
            <span v-if="credStatus.configured" class="cred-ok">
              ✓ 已保存 {{ credStatus.account }}（{{ credStatus.backend === 'keyring' ? '系统凭据库' : '本地文件' }}）
            </span>
            <span v-else class="cred-none">未配置——提交微信前需要填写</span>
            <div class="btn-group">
              <button class="btn-sm" :disabled="savingCred || !pubAccount || !pubPassword" @click="saveCredentials">
                {{ savingCred ? '保存中…' : '保存账号密码' }}
              </button>
              <button v-if="credStatus.configured" class="btn-sm btn-reset" :disabled="savingCred" @click="clearCredentials">
                清除
              </button>
            </div>
          </div>
          <p v-if="credError" class="cred-error">{{ credError }}</p>
          <p v-if="credSaved" class="cred-saved">✓ 已保存，之后发布将自动登录</p>
        </div>
      </div>

      <!-- 浏览器模式 -->
      <div class="section">
        <h3 class="section-title">浏览器模式</h3>
        <div class="bm-opts">
          <label class="bm-opt" :class="{ active: !browserHeadless }">
            <input type="radio" :value="false" v-model="browserHeadless" />
            <span class="bm-name">🖥️ 有头浏览器（默认）</span>
            <span class="bm-desc">提交/同步时弹出浏览器窗口，能亲眼看到软件在平台上做的每一步</span>
          </label>
          <label class="bm-opt" :class="{ active: browserHeadless }">
            <input type="radio" :value="true" v-model="browserHeadless" />
            <span class="bm-name">👻 无头浏览器</span>
            <span class="bm-desc">后台静默运行不弹窗，已实测平台可用；遇到异常再切回有头</span>
          </label>
        </div>
        <p v-if="bmSaved" class="cred-saved">✓ 已保存</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useEngineStore } from '../store/engine'
import WizardStepBase from './WizardStepBase.vue'
import WizardStepMode from './WizardStepMode.vue'
import WizardStepChar from './WizardStepChar.vue'
import WizardStepPref from './WizardStepPref.vue'

const store = useEngineStore()
const tab = ref('gen')

// ---- 发布账号（凭据管理）----
const isWindows = typeof navigator !== 'undefined' && /windows/i.test(navigator.userAgent)
const pubAccount = ref('')
const pubPassword = ref('')
const credStatus = ref({ configured: false, account: '', backend: '' })
const savingCred = ref(false)
const credError = ref('')
const credSaved = ref(false)

async function switchPublish() {
  tab.value = 'publish'
  credSaved.value = false
  if (!window.api) return
  try {
    const res = await window.api.send('publish_credentials_status')
    if (res && res.status === 'ok') credStatus.value = res.data
  } catch { /* 状态加载失败不阻塞 */ }
}

// ---- 浏览器模式（有头=能看见软件操作 / 无头=后台静默）----
const browserHeadless = ref(false)
const bmSaved = ref(false)
onMounted(() => {
  if (store.prefs) browserHeadless.value = !!store.prefs.browser_headless
})
watch(browserHeadless, async (v) => {
  if (!store.prefs || store.prefs.browser_headless === v) return
  store.prefs.browser_headless = v
  try {
    await store.savePrefs(store.prefs)
    bmSaved.value = true
    setTimeout(() => (bmSaved.value = false), 2000)
  } catch { /* 保存失败不打断界面 */ }
})

// ---- Prompt 方案管理 ----
const promptSets = ref([])
const activePromptSet = ref('')
const editing = ref(null)
const psSavedTip = ref('')

async function switchPrompts() {
  tab.value = 'prompts'
  psSavedTip.value = ''
  editing.value = null
  await loadPromptSets()
}

async function loadPromptSets() {
  if (!window.api) return
  try {
    const res = await window.api.send('list_prompt_sets')
    if (res?.status === 'ok') {
      promptSets.value = res.data.sets || []
      activePromptSet.value = res.data.active || ''
    }
  } catch { /* 静默 */ }
}

function editSet(s) {
  editing.value = { ...s }
  psSavedTip.value = ''
}

function newSet() {
  editing.value = { id: '', name: '新方案', style_block: '', combo_extra: '', story_extra: '', ref_extra: '' }
}

function dupSet(s) {
  editing.value = { ...s, id: '', name: s.name + ' 副本' }
}

async function setDefault(s) {
  if (!window.api) return
  const res = await window.api.send('save_prompt_set', { set: s, is_default: true })
  if (res?.status === 'ok') {
    activePromptSet.value = res.data.set.id
    // 同步进当前 prefs（向导/生成读同一份）
    if (store.prefs) store.prefs.prompt_set_id = res.data.set.id
    await loadPromptSets()
  }
}

async function saveSet(asNew = false) {
  if (!window.api || !editing.value) return
  const payload = { ...editing.value }
  if (asNew) payload.id = ''
  const res = await window.api.send('save_prompt_set', {
    set: payload, is_default: !asNew && payload.id === activePromptSet.value,
  })
  if (res?.status === 'ok') {
    editing.value = res.data.set
    psSavedTip.value = '✓ 已保存' + (res.data.active === res.data.set.id ? '（默认方案）' : '')
    await loadPromptSets()
  }
}

async function deleteSet(s) {
  if (!window.api || !confirm(`确定删除方案「${s.name}」？`)) return
  const res = await window.api.send('delete_prompt_set', { id: s.id })
  if (res?.status === 'ok') {
    if (editing.value?.id === s.id) editing.value = null
    await loadPromptSets()
  }
}

onMounted(() => { if (!window.api) return })

async function saveCredentials() {
  if (!window.api || !pubAccount.value || !pubPassword.value) return
  savingCred.value = true
  credError.value = ''
  credSaved.value = false
  try {
    const res = await window.api.send('save_publish_credentials', {
      account: pubAccount.value, password: pubPassword.value,
    })
    if (res && res.status === 'ok') {
      pubAccount.value = ''
      pubPassword.value = ''
      credSaved.value = true
      const st = await window.api.send('publish_credentials_status')
      if (st && st.status === 'ok') credStatus.value = st.data
    } else {
      credError.value = (res && res.errors && res.errors[0] && res.errors[0].message) || '保存失败'
    }
  } catch (e) {
    credError.value = (e && e.message) || '保存失败'
  } finally {
    savingCred.value = false
  }
}

async function clearCredentials() {
  if (!window.api) return
  savingCred.value = true
  credError.value = ''
  credSaved.value = false
  try {
    await window.api.send('clear_publish_credentials')
    credStatus.value = { configured: false, account: '', backend: '' }
  } catch (e) {
    credError.value = (e && e.message) || '清除失败'
  } finally {
    savingCred.value = false
  }
}

async function save() {
  await store.savePrefs(store.prefs)
}
function back() {
  store.phase = 'main'
}
</script>

<style scoped>
.settings { padding: 32px; max-width: 720px; margin: 0 auto; }

header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.back {
  background: var(--card);
  border: 1.5px solid var(--paper);
  border-radius: var(--r-pill);
  padding: 8px 18px;
  color: var(--forest);
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.back:hover { border-color: var(--sage); transform: translateX(-2px); }

h2 {
  margin: 0;
  font-family: var(--font-head);
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}

/* 顶部 tab */
.tab-bar { display: flex; gap: 8px; margin-bottom: 18px; }

/* ---- Prompt 方案管理 ---- */
.ps-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
.ps-item {
  padding: 14px; border: 1.5px solid var(--paper); border-radius: 12px;
  background: var(--card); cursor: pointer; transition: all .15s ease;
}
.ps-item:hover { border-color: var(--sage); }
.ps-item.active { border-color: var(--forest); box-shadow: var(--shadow-soft); }
.ps-item.add { border-style: dashed; color: var(--muted-soft); text-align: center; }
.ps-head { display: flex; align-items: center; gap: 6px; }
.ps-name { font-weight: 700; font-size: 13.5px; color: var(--ink); }
.ps-badge {
  font-size: 10px; font-weight: 700; padding: 1px 8px; border-radius: 999px;
  background: var(--forest); color: #fff;
}
.ps-badge.dim { background: var(--paper); color: var(--muted); }
.ps-meta {
  margin: 8px 0; font-size: 11px; color: var(--muted-soft);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ps-ops { display: flex; gap: 6px; }
.ps-btn {
  padding: 4px 10px; font-size: 11px; font-weight: 700; cursor: pointer;
  border: 1px solid var(--line); border-radius: 999px; background: var(--card);
  color: var(--forest);
}
.ps-btn.primary { border-color: var(--forest); }
.ps-btn.danger { color: var(--brick); }
.ps-editor {
  width: 100%; padding: 10px 12px; border: 1.5px solid var(--paper);
  border-radius: 10px; font-family: Consolas, monospace; font-size: 12px;
  background: var(--card); resize: vertical; box-sizing: border-box;
}
.row-actions { display: flex; gap: 10px; }
.tab {
  flex: 1;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 11px 10px;
  border: 1.5px solid var(--paper); border-radius: var(--r-md);
  background: var(--card); color: var(--muted);
  font-size: 13.5px; font-weight: 700; cursor: pointer;
  transition: all .15s ease;
}
.tab:hover { border-color: var(--sage); }
.tab.active { background: var(--forest); color: var(--white); border-color: var(--forest); }
.tab-dot { width: 8px; height: 8px; border-radius: 50%; }
.tab-dot.ok { background: var(--sage); }
.tab.active .tab-dot.ok { background: var(--sage); }
.tab-dot.warn { background: #f0a35e; }

.settings-body { display: flex; flex-direction: column; gap: 16px; }

/* 分区 sticker-card */
.section {
  background: var(--card);
  padding: 24px;
  border-radius: var(--r-card);
  border: 1.5px solid var(--paper);
  box-shadow: var(--shadow-card);
}
.section-title {
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1.5px dashed var(--paper);
  font-family: var(--font-head);
  font-size: 16px;
  font-weight: 700;
  color: var(--forest);
}

/* 保存按钮（sage 绿） */
.save {
  align-self: center;
  padding: 13px 44px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--sage);
  color: var(--forest);
  cursor: pointer;
  margin-top: 8px;
  font-family: var(--font-head);
  font-weight: 700;
  font-size: 15px;
  box-shadow: 0 8px 20px rgba(175, 205, 168, .5);
  transition: all .15s ease;
}
.save:hover { transform: translateY(-1px); filter: brightness(1.03); }
.save:active { transform: translateY(1px); }
.settings-error { padding: 12px 16px; border-radius: var(--r-md); background: rgba(181,72,42,.12); color: var(--brick); font-size: 13px; font-weight: 700; }

/* 发布账号区 */
.pub-account-hint { margin: 0 0 14px; color: var(--muted); font-size: 12.5px; line-height: 1.7; }
.pub-account-form .field { margin: 10px 0; }
.field-label { display: block; margin-bottom: 6px; font-weight: 600; color: var(--ink); font-size: 13px; }
.pub-input {
  width: 100%; max-width: 380px;
  padding: 10px 14px;
  border: 1.5px solid var(--paper);
  border-radius: var(--r-md);
  background: var(--bg-cream);
  font-size: 13px;
  color: var(--ink);
  font-family: var(--font-body);
}
.pub-input:focus { outline: none; border-color: var(--sage); }
.pub-account-actions { display: flex; align-items: center; gap: 12px; margin-top: 8px; flex-wrap: wrap; }
.cred-ok { color: var(--correct); font-size: 12.5px; font-weight: 600; }
.cred-none { color: #c07830; font-size: 12.5px; font-weight: 600; }
.btn-group { display: flex; gap: 8px; margin-left: auto; }
.btn-sm {
  padding: 8px 16px; border: 1.5px solid var(--forest); border-radius: var(--r-pill);
  background: var(--card); color: var(--forest); cursor: pointer;
  font-weight: 600; font-size: 12.5px; white-space: nowrap;
}
.btn-sm:hover:not(:disabled) { background: var(--forest); color: var(--white); }
.btn-sm:disabled { opacity: .5; cursor: not-allowed; }
.btn-reset { border-color: var(--line); color: var(--muted); }
.btn-reset:hover:not(:disabled) { background: var(--paper); color: var(--ink); }
.cred-error { color: var(--brick); font-size: 12.5px; margin: 8px 0 0; }
.cred-saved { color: var(--correct); font-size: 12.5px; margin: 8px 0 0; font-weight: 600; }

/* 浏览器模式选项 */
.bm-opts { display: flex; flex-direction: column; gap: 10px; }
.bm-opt {
  display: grid; grid-template-columns: auto auto 1fr; align-items: baseline;
  gap: 8px; padding: 10px 12px; border: 1.5px solid var(--line);
  border-radius: 10px; cursor: pointer; transition: border-color .15s, background .15s;
}
.bm-opt:hover { border-color: var(--forest); }
.bm-opt.active { border-color: var(--forest); background: rgba(76, 140, 43, .07); }
.bm-opt input { margin: 0; }
.bm-name { font-size: 13.5px; font-weight: 600; }
.bm-desc { font-size: 12px; color: var(--muted); }
</style>
