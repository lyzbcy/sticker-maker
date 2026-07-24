<template>
  <div class="step-codex">
    <div v-if="!store.codexStatus" class="checking">检测中…</div>
    <div v-else-if="store.codexStatus.image_ready" class="ok">
      <p>✅ codex 可用</p>
      <p class="hint">已检测到 codex，图片生成可用。</p>
      <button class="btn" @click="store.checkCodex">重新检测</button>
    </div>
    <div v-else class="fail">
      <p>❌ {{ store.codexStatus.guidance_msg || 'codex 不可用' }}</p>
      <div class="guide">
        <p>安装步骤：</p>
        <ol>
          <li>打开终端运行：<code>npm i -g @openai/codex</code></li>
          <li>运行：<code>codex login</code></li>
          <li>回来点重新检测</li>
        </ol>
      </div>
      <button class="btn" @click="store.checkCodex">我已安装，重新检测</button>
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
.ok { color: #2c8a3e; } .fail { color: #c33; }
.guide { background: #f6f8fa; padding: 12px; border-radius: 6px; margin: 12px 0; }
code { background: #eee; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
.btn { margin-top: 10px; padding: 8px 16px; border: none; border-radius: 6px; background: #4a90d9; color: #fff; cursor: pointer; }
</style>
