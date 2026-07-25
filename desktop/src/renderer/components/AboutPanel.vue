<template>
  <div class="about">
    <header>
      <button class="back" @click="$emit('back')">← 返回</button>
      <h2>关于</h2>
    </header>
    <div class="body">
      <!-- 信息卡片 -->
      <div class="info-card">
        <div class="info-emoji">🎨</div>
        <h3>表情包一键制作</h3>
        <p class="version">版本 {{ version }}</p>
        <p class="author">作者：{{ promo.author_name }}</p>
        <p class="tagline">把你的表情包创意变成现实 ✨</p>
        <button class="update-btn" @click="checkUpdates">手动检查更新</button>
      </div>

      <!-- 二维码区 -->
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

const version = ref('0.2.0')
const promo = ref({ reward_qr: null, group_qr: null, sticker_qr: null, author_name: '捞鱼真不吃鱼' })

const hasQr = computed(() => promo.value.reward_qr || promo.value.group_qr || promo.value.sticker_qr)

function imgSrc(path) {
  return path && window.api?.toFileUrl ? window.api.toFileUrl(path) : (path ? `file://${path}` : '')
}

function onImgError(e) {
  // 图片加载失败隐藏该项
  e.target.parentElement.style.display = 'none'
}

onMounted(async () => {
  if (!window.api) return
  try {
    const versionRes = await window.api.send('get_version')
    if (versionRes?.status === 'ok') version.value = versionRes.data.version
    const res = await window.api.send('load_promotion')
    if (res && res.status === 'ok' && res.data) {
      promo.value = res.data
    }
  } catch (e) {
    // 静默（推广是锦上添花）
  }
})
async function checkUpdates() {
  if (window.api?.checkForUpdates) await window.api.checkForUpdates()
}
</script>
<style scoped>
.about { padding: 32px; max-width: 600px; margin: 0 auto; }

header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
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

.body { display: flex; flex-direction: column; gap: 18px; }

/* 信息卡片（大圆角 + 柔光阴影） */
.info-card {
  padding: 32px 24px;
  text-align: center;
  background: var(--hero-gradient);
  border-radius: var(--r-card);
  box-shadow: var(--shadow-card);
}
.info-emoji { font-size: 48px; margin-bottom: 8px; }
.info-card h3 {
  margin: 0 0 8px;
  font-family: var(--font-head);
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}
.version { margin: 0 0 4px; color: var(--forest); font-weight: 600; font-size: 13px; }
.author { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
.tagline { margin: 0; color: var(--forest); font-size: 14px; font-weight: 600; }
.update-btn { margin-top: 16px; padding: 9px 16px; border: 1.5px solid var(--sage); border-radius: var(--r-pill); background: var(--card); color: var(--forest); cursor: pointer; font-weight: 700; }

/* 二维码区 */
.qr-section {
  padding: 24px;
  background: var(--card);
  border-radius: var(--r-card);
  border: 1.5px solid var(--paper);
  box-shadow: var(--shadow-card);
}
.qr-section h3 {
  margin: 0 0 16px;
  font-family: var(--font-head);
  font-size: 16px;
  color: var(--forest);
}
.qr-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.qr-item {
  text-align: center;
  padding: 12px 8px;
  background: var(--bg-cream);
  border-radius: var(--r-md);
  transition: all .15s ease;
}
.qr-item:hover { transform: translateY(-2px); box-shadow: var(--shadow-soft); }
.qr-item img {
  width: 100%;
  max-width: 130px;
  border-radius: var(--r-sm);
}
.qr-item p {
  margin: 8px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--forest);
}

.hint { color: var(--muted-faint); font-size: 13px; text-align: center; }
</style>
