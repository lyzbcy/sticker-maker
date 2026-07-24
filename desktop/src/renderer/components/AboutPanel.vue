<template>
  <div class="about">
    <header>
      <button class="back" @click="$emit('back')">← 返回</button>
      <h2>关于</h2>
    </header>
    <div class="body">
      <div class="info">
        <h3>表情包一键制作</h3>
        <p>版本 {{ version }}</p>
        <p>作者：{{ author }}</p>
      </div>
      <div class="qr-section" v-if="hasQr">
        <h3>关注作者</h3>
        <div class="qr-grid">
          <div class="qr-item" v-if="qr.reward">
            <img :src="'file://' + qr.reward" alt="赞赏" />
            <p>赞赏</p>
          </div>
          <div class="qr-item" v-if="qr.group">
            <img :src="'file://' + qr.group" alt="入群" />
            <p>入群</p>
          </div>
          <div class="qr-item" v-if="qr.sticker">
            <img :src="'file://' + qr.sticker" alt="表情包" />
            <p>表情包</p>
          </div>
        </div>
      </div>
      <p class="hint" v-else>（作者推广位未配置）</p>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'

defineEmits(['back'])

const version = ref('0.1.0')
const author = ref('捞鱼真不吃鱼')
const qr = ref({ reward: null, group: null, sticker: null })
const hasQr = ref(false)

onMounted(async () => {
  // 从配置加载三码（默认空，开发者本地配置后展示）
  // 这里简化：从 prefs 或本地配置读，未来扩展
})
</script>
<style scoped>
.about { padding: 24px; max-width: 600px; margin: 0 auto; }
header { display: flex; align-items: center; gap: 16px; }
.back { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 16px; }
.info { background: #fff; padding: 16px; border-radius: 8px; margin: 16px 0; }
.qr-section { background: #fff; padding: 16px; border-radius: 8px; }
.qr-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
.qr-item { text-align: center; }
.qr-item img { width: 100%; max-width: 140px; border-radius: 8px; }
.qr-item p { margin: 6px 0 0; font-size: 13px; color: #666; }
.hint { color: #999; font-size: 13px; text-align: center; }
</style>
