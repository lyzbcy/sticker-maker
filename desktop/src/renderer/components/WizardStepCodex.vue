<template>
  <div class="step-codex">
    <!-- 未检测 -->
    <div v-if="!store.codexStatus" class="checking">检测中…</div>

    <!-- 已就绪 -->
    <div v-else-if="store.codexStatus.image_ready" class="ok">
      <p>✅ codex 可用</p>
      <p class="hint">已检测到 codex，图片生成可用。</p>
      <button class="btn" @click="store.checkCodex">重新检测</button>
    </div>

    <!-- 未就绪：一键安装 -->
    <div v-else class="fail">
      <p>❌ {{ store.codexStatus.guidance_msg || 'codex 不可用' }}</p>

      <!-- 一键安装 -->
      <div class="install-section" v-if="!store.installing">
        <p class="install-desc">codex 是生图引擎，需要先安装。点下面按钮一键安装（全自动）：</p>
        <button class="btn btn-install" @click="store.installCodex">📦 一键安装 codex</button>
        <p class="hint">安装约需 1-3 分钟，会下载官方安装包。请保持网络畅通。</p>
      </div>

      <!-- 安装中：实时日志 -->
      <div class="installing" v-else>
        <p class="installing-title">⏳ 正在安装，请稍候…</p>
        <div class="log-box">
          <p v-for="(line, i) in store.installLog" :key="i" class="log-line">{{ line }}</p>
          <p v-if="store.installLog.length === 0" class="log-line dim">等待输出...</p>
        </div>
      </div>

      <!-- 手动安装指引（折叠） -->
      <details class="manual-guide" v-if="!store.installing">
        <summary>安装遇到问题？看手动安装步骤</summary>
        <div class="guide">
          <p>打开终端，运行：</p>
          <pre><code>curl -fsSL https://chatgpt.com/codex/install.sh | sh</code></pre>
          <p>或（已装 node）：</p>
          <pre><code>npm i -g @openai/codex</code></pre>
          <p>然后运行 <code>codex</code> 按提示登录。</p>
          <p>完成后回来点 [重新检测]。</p>
        </div>
      </details>

      <button class="btn" v-if="!store.installing" @click="store.checkCodex">我已安装，重新检测</button>

      <!-- 安装失败的提示 -->
      <div class="install-error" v-if="store.lastError && !store.installing && !store.codexStatus.image_ready">
        <p v-for="(e, i) in store.lastError" :key="i">{{ e.message }}</p>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted } from 'vue'
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
onMounted(() => store.checkCodex())
</script>
<style scoped>
.ok { color: #2c8a3e; }
.fail { color: #c33; }
.install-section { background: #f6f8fa; padding: 16px; border-radius: 8px; margin: 12px 0; }
.install-desc { color: #333; margin: 0 0 12px; }
.btn { margin-top: 10px; padding: 8px 16px; border: none; border-radius: 6px; background: #4a90d9; color: #fff; cursor: pointer; }
.btn-install { background: linear-gradient(135deg, #4a90d9, #7ac67d); font-size: 15px; padding: 12px 28px; }
.btn-install:hover { transform: translateY(-1px); }
.hint { color: #888; font-size: 13px; margin-top: 8px; }
.installing { margin: 12px 0; }
.installing-title { color: #4a90d9; font-weight: 600; }
.log-box { background: #1e1e1e; color: #ddd; padding: 12px; border-radius: 6px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px; margin-top: 8px; }
.log-line { margin: 2px 0; word-break: break-all; }
.log-line.dim { color: #666; }
.manual-guide { margin-top: 16px; }
.manual-guide summary { color: #4a90d9; cursor: pointer; font-size: 13px; }
.guide { background: #f6f8fa; padding: 12px; border-radius: 6px; margin-top: 8px; color: #555; font-size: 13px; }
.guide code, pre code { background: #eee; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
pre { background: #2d2d2d; color: #f8f8f2; padding: 8px; border-radius: 4px; overflow-x: auto; }
.install-error { background: #fff0f0; padding: 10px; border-radius: 6px; margin-top: 12px; color: #c33; font-size: 13px; }
</style>
