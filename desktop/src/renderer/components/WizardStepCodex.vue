<template>
  <button class="skip-check" @click="$emit('skip-check')">稍后检测，先跳过 →</button>
    <div class="step-codex">
    <!-- 未检测 -->
    <div v-if="!store.codexStatus" class="checking">检测中…</div>

    <!-- 已就绪 -->
    <div v-else-if="store.codexStatus.image_ready" class="ok-card">
      <div class="state-icon ok">✓</div>
      <div class="state-text">
        <p class="state-title">codex 可用</p>
        <p class="hint">生图工具和登录检测通过；实际生成以账号额度、网络和生成结果为准。</p>
      </div>
      <button class="btn-ghost" @click="store.checkCodex">重新检测</button>
    </div>

    <!-- 未就绪：一键安装 -->
    <div v-else class="fail-wrap">
      <div class="fail-card">
        <div class="state-icon fail">!</div>
        <div class="state-text">
          <p class="state-title fail-title">{{ store.codexStatus.guidance_msg || 'codex 不可用' }}</p>
          <p class="hint">{{ store.codexStatus.needs_repair ? '请修复缺失的生图组件，再重新检测。' : store.codexStatus.installed ? '已经安装，只需登录后重新检测。' : '先安装生图工具，再登录自己的账号。' }}</p>
        </div>
      </div>

      <!-- 一键安装 -->
      <div class="install-section" v-if="!store.installing && (!store.codexStatus.installed || store.codexStatus.needs_repair)">
        <p class="install-desc">codex 是生图引擎，需要先安装。点下面按钮一键安装（全自动）：</p>
        <button class="btn btn-install" @click="store.installCodex">{{ store.codexStatus.needs_repair ? '修复生图工具' : '📦 一键安装 codex' }}</button>
        <p class="hint">会下载官方压缩安装包，耗时取决于网络；下面显示真实下载进度。请保持网络畅通。</p>
      </div>

      <div v-if="store.codexStatus.installed && !store.codexStatus.needs_repair && !store.installing" class="install-section">
        <button class="btn" @click="loginCodex">打开登录窗口</button>
        <p class="hint">请在新打开的窗口完成登录，再点「我已登录，重新检测」。生成需要可用的账号额度。</p>
        <p v-if="loginError" role="alert">{{ loginError }}</p>
      </div>
      <!-- 安装中：实时日志 -->
      <div class="installing" v-if="store.installing">
        <p class="installing-title">⏳ 正在安装，请稍候…</p>
        <div class="log-box">
          <p v-for="(line, i) in store.installLog" :key="i" class="log-line">{{ line }}</p>
          <p v-if="store.installLog.length === 0" class="log-line dim">等待输出...</p>
        </div>
      </div>

      <!-- 手动安装指引（折叠，按平台显示） -->
      <details class="manual-guide" v-if="!store.installing">
        <summary>安装遇到问题？看手动安装步骤</summary>
        <div class="guide" v-if="isWindows">
          <p>推荐使用官方 Windows 安装器（<a href="https://chatgpt.com/codex/install.ps1" target="_blank" rel="noopener" style="color:var(--forest)">chatgpt.com/codex/install.ps1</a>），或在 PowerShell 中运行：</p>
          <pre><code>powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"</code></pre>
          <p>然后运行 <code>codex</code> 按提示登录。</p>
          <p>完成后回来点 [重新检测]。</p>
        </div>
        <div class="guide" v-else>
          <p>打开终端，运行：</p>
          <pre><code>curl -fsSL https://chatgpt.com/codex/install.sh | sh</code></pre>
          <p>或（已装 node）：</p>
          <pre><code>npm i -g @openai/codex</code></pre>
          <p>然后运行 <code>codex</code> 按提示登录。</p>
          <p>完成后回来点 [重新检测]。</p>
        </div>
      </details>

      <button class="btn-ghost" v-if="!store.installing" @click="store.checkCodex">我已登录，重新检测</button>

      <!-- 安装失败的提示 -->
      <div class="install-error" v-if="store.lastError && !store.installing && !store.codexStatus.image_ready">
        <p v-for="(e, i) in store.lastError" :key="i">{{ e.message }}</p>
      </div>
    </div>
  </div>
</template>
<script setup>
defineEmits(['skip-check'])
import { onMounted, ref } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
const loginError = ref('')
async function loginCodex() {
  loginError.value = ''
  try {
    const res = await window.api?.send('login_codex')
    if (res?.status !== 'ok') loginError.value = res?.errors?.[0]?.message || '请在终端运行 codex login，再回来重新检测。'
  } catch (e) { loginError.value = e.message }
}
// 平台检测（渲染层）：Windows 显示 npm 指引，Mac 显示官方脚本指引
const isWindows = typeof navigator !== 'undefined' &&
  (navigator.userAgentData?.platform?.toLowerCase().includes('win') ||
   /windows/i.test(navigator.userAgent))
onMounted(() => store.checkCodex())
</script>
<style scoped>
.checking {
  padding: 20px;
  text-align: center;
  color: var(--muted-soft);
  font-size: 14px;
}

/* 成功卡片（sage 绿） */
.ok-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: rgba(175, 205, 168, .28);
  border: 1.5px solid var(--sage);
  border-radius: var(--r-lg);
}
.state-icon {
  flex-shrink: 0;
  width: 36px; height: 36px;
  display: grid; place-items: center;
  border-radius: 50%;
  font-weight: 700;
  font-size: 18px;
  color: var(--white);
}
.state-icon.ok { background: var(--correct); }
.state-text { flex: 1; min-width: 0; }
.state-title { margin: 0; font-weight: 700; color: var(--forest); font-size: 15px; }
.hint { margin: 4px 0 0; color: var(--muted); font-size: 13px; }

.btn-ghost {
  padding: 8px 18px;
  border: 1.5px solid var(--forest);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--forest);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s ease;
  white-space: nowrap;
}
.btn-ghost:hover { background: var(--forest); color: var(--white); transform: translateY(-1px); }

/* 失败包裹 */
.fail-wrap { display: flex; flex-direction: column; gap: 14px; }

/* 失败卡片（brick 红，但柔和不刺眼） */
.fail-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: rgba(181, 72, 42, .10);
  border: 1.5px solid rgba(181, 72, 42, .35);
  border-radius: var(--r-lg);
}
.state-icon.fail { background: var(--brick); }
.fail-title { color: var(--brick); }

/* 一键安装区 */
.install-section {
  padding: 18px 20px;
  background: var(--paper);
  border-radius: var(--r-lg);
}
.install-desc { margin: 0 0 14px; color: var(--ink); font-size: 14px; }

.btn {
  padding: 11px 22px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--forest);
  color: var(--white);
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  transition: all .15s ease;
  box-shadow: var(--shadow-btn);
}
.btn:hover { background: var(--forest-hover); transform: translateY(-1px); }
.btn:active { transform: translateY(1px); }

.btn-install {
  background: linear-gradient(135deg, var(--forest), var(--correct));
  font-size: 15px;
  padding: 13px 30px;
}

/* 安装中日志（黑底终端，保持原样是对的） */
.installing { display: flex; flex-direction: column; gap: 8px; }
.installing-title { color: var(--forest); font-weight: 700; margin: 0; }
.log-box {
  background: #1e1e1e;
  color: #ddd;
  padding: 14px;
  border-radius: var(--r-sm);
  max-height: 200px;
  overflow-y: auto;
  font-family: "SF Mono", "Menlo", monospace;
  font-size: 12px;
  line-height: 1.6;
}
.log-line { margin: 2px 0; word-break: break-all; }
.log-line.dim { color: #666; }

/* 手动安装指引 */
.manual-guide { font-size: 13px; }
.manual-guide summary {
  color: var(--forest);
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}
.manual-guide summary:hover { color: var(--forest-hover); }
.guide {
  background: var(--paper);
  padding: 14px;
  border-radius: var(--r-md);
  margin-top: 8px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}
.guide code, pre code {
  background: rgba(30, 58, 36, .08);
  padding: 2px 7px;
  border-radius: var(--r-sm);
  font-family: "SF Mono", "Menlo", monospace;
  font-size: 12px;
}
pre {
  background: #2d2d2d;
  color: #f8f8f2;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  overflow-x: auto;
  font-family: "SF Mono", "Menlo", monospace;
  font-size: 12px;
}

/* 安装错误 */
.install-error {
  background: rgba(181, 72, 42, .10);
  border: 1.5px solid rgba(181, 72, 42, .3);
  padding: 12px 14px;
  border-radius: var(--r-md);
  color: var(--brick);
  font-size: 13px;
}
.install-error p { margin: 2px 0; }
.skip-check { border: 0; background: none; color: var(--muted, #888); cursor: pointer;
  font-size: 12.5px; text-decoration: underline; margin-left: 10px; }
</style>
