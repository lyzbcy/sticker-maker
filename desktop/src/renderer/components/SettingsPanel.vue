<template>
  <div class="settings">
    <header>
      <button class="back" @click="back">← 返回</button>
      <h2>设置</h2>
    </header>

    <!-- 顶部 tab：一个主题一屏，不再长条滚动 -->
    <div class="tab-bar">
      <button class="tab" :class="{ active: tab === 'gen' }" @click="tab = 'gen'">🎨 生图设置</button>
      <button class="tab" :class="{ active: tab === 'publish' }" @click="switchPublish">
        📤 发布账号
        <span v-if="credStatus.configured" class="tab-dot ok" title="已配置"></span>
        <span v-else class="tab-dot warn" title="未配置，提交微信前需要填写"></span>
      </button>
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
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
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
</style>
