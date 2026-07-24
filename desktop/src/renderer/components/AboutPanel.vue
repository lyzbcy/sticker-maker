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
        <p>作者：{{ promo.author_name }}</p>
        <p class="hint">把你的表情包创意变成现实 ✨</p>
      </div>
      <div class="qr-section" v-if="hasQr">
        <h3>关注作者</h3>
        <div class="qr-grid">
          <div class="qr-item" v-if="promo.reward_qr">
            <img :src="imgSrc(promo.reward_qr)" alt="赞赏" @error="onImgError" />
            <p>赞赏</p>
          </div>
          <div class="qr-item" v-if="promo.group_qr">
            <img :src="imgSrc(promo.group_qr)" alt="入群" @error="onImgError" />
            <p>入群</p>
          </div>
          <div class="qr-item" v-if="promo.sticker_qr">
            <img :src="imgSrc(promo.sticker_qr)" alt="表情包" @error="onImgError" />
            <p>表情包</p>
          </div>
        </div>
      </div>
      <p class="hint" v-else>（作者推广位未配置）</p>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'

defineEmits(['back'])

const version = ref('0.1.0')
const promo = ref({ reward_qr: null, group_qr: null, sticker_qr: null, author_name: '捞鱼真不吃鱼' })

const hasQr = computed(() => promo.value.reward_qr || promo.value.group_qr || promo.value.sticker_qr)

function imgSrc(path) {
  // 本地图片：file:// 协议；打包后 resources 路径也走 file://
  return path ? 'file://' + path : ''
}

function onImgError(e) {
  // 图片加载失败隐藏该项
  e.target.parentElement.style.display = 'none'
}

onMounted(async () => {
  if (!window.api) return
  try {
    const res = await window.api.send('load_promotion')
    if (res && res.status === 'ok' && res.data) {
      promo.value = res.data
    }
  } catch (e) {
    // 静默（推广是锦上添花）
  }
})
</script>
<style scoped>
.about { padding: 24px; max-width: 600px; margin: 0 auto; }
header { display: flex; align-items: center; gap: 16px; }
.back { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 16px; }
.info { background: #fff; padding: 16px; border-radius: 8px; margin: 16px 0; }
.info h3 { margin-top: 0; }
.qr-section { background: #fff; padding: 16px; border-radius: 8px; }
.qr-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
.qr-item { text-align: center; }
.qr-item img { width: 100%; max-width: 140px; border-radius: 8px; }
.qr-item p { margin: 6px 0 0; font-size: 13px; color: #666; }
.hint { color: #999; font-size: 13px; text-align: center; }
</style>
