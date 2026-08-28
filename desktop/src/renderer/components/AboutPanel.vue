<template>
  <div class="about">
    <header>
      <button class="back" @click="$emit('back')">← 返回</button>
      <h2>关于</h2>
    </header>
    <div class="body">
      <!-- 作者卡片（prompt「个人推广页」：头像 + 工作室署名 + 一键直达链接） -->
      <div class="author-card">
        <img v-if="promo.avatar_url" class="avatar" :src="promo.avatar_url" alt="作者头像"
             @error="promo.avatar_url = ''" />
        <div class="author-main">
          <h3>{{ promo.studio_name || '表情包一键制作' }}</h3>
          <p class="author-line">
            {{ promo.author_name }} · 一个弱小但有梦想的开发者 🐟
          </p>
          <p class="version-line">表情包一键制作 · 版本 {{ version }}</p>
        </div>
      </div>

      <!-- 一键直达（减少交互步骤：点一下就到） -->
      <div class="quick-links">
        <button class="link-btn" @click="openExternal(promo.homepage_url)">🏠 个人主页</button>
        <button class="link-btn star" @click="openExternal(promo.repo_url)">⭐ 给个 Star</button>
        <button class="link-btn" @click="openExternal(promo.discussions_url)">💬 提点建议</button>
        <button class="link-btn" @click="checkUpdates">🔄 检查更新</button>
      </div>
      <p class="star-hint">如果这个软件帮到了你，一个 Star 对作者很有帮助 ✨</p>

      <!-- 自家表情走马灯（润物细无声：我们是表情包工厂，界面用自家表情） -->
      <div class="sticker-strip" v-if="featured.length">
        <div class="strip-inner">
          <img v-for="(f, i) in stripStickers" :key="i + f.path" :src="fileUrl(f.path)"
               :alt="f.name" :title="f.name" />
        </div>
      </div>

      <!-- 二维码区 -->
      <div class="qr-section" v-if="hasQr">
        <h3>关注作者</h3>
        <div class="qr-grid">
          <div class="qr-item" v-if="promo.reward_qr">
            <img :src="imgSrc(promo.reward_qr)" alt="赞赏" @error="onImgError" />
            <p>请喝杯咖啡 ☕</p>
          </div>
          <div class="qr-item" v-if="promo.group_qr">
            <img :src="imgSrc(promo.group_qr)" alt="入群" @error="onImgError" />
            <p>加入 QQ 群</p>
          </div>
          <div class="qr-item" v-if="promo.sticker_qr">
            <img :src="imgSrc(promo.sticker_qr)" alt="表情包" @error="onImgError" />
            <p>微信表情包</p>
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

const version = ref('…')
const promo = ref({
  reward_qr: null, group_qr: null, sticker_qr: null,
  author_name: '捞鱼真不吃鱼', studio_name: '捞鱼工作室',
  homepage_url: 'https://lyzbcy.github.io/',
  avatar_url: 'https://s41.ax1x.com/2025/12/05/pZmPZPH.png',
  repo_url: 'https://github.com/lyzbcy/sticker-maker',
  discussions_url: 'https://github.com/lyzbcy/sticker-maker/discussions',
})
const featured = ref([])

const hasQr = computed(() => promo.value.reward_qr || promo.value.group_qr || promo.value.sticker_qr)
// 走马灯用 10 张，不够就重复凑双份循环
const stripStickers = computed(() => {
  const list = featured.value.length ? featured.value : []
  return list.length >= 5 ? [...list, ...list.slice(0, 10 - list.length)] : []
})

function imgSrc(path) {
  return path && window.api?.toFileUrl ? window.api.toFileUrl(path) : (path ? `file://${path}` : '')
}
const fileUrl = imgSrc

function openExternal(url) {
  if (url && window.api?.openExternal) window.api.openExternal(url)
}

function onImgError(e) {
  e.target.parentElement.style.display = 'none'
}

onMounted(async () => {
  if (!window.api) return
  try {
    const versionRes = await window.api.send('get_version')
    if (versionRes?.status === 'ok') version.value = versionRes.data.version
    const res = await window.api.send('load_promotion')
    if (res && res.status === 'ok' && res.data) {
      promo.value = { ...promo.value, ...res.data }
    }
    const feat = await window.api.send('featured', { n: 10 })
    if (feat && feat.status === 'ok') featured.value = feat.data.sample || []
  } catch (e) {
    // 静默（推广是锦上添花）
  }
})
async function checkUpdates() {
  if (window.api?.checkForUpdates) await window.api.checkForUpdates()
}
</script>
<style scoped>
.about { padding: 32px; max-width: 640px; margin: 0 auto; }

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

/* 作者卡片 */
.author-card {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 24px;
  background: var(--hero-gradient);
  border-radius: var(--r-card);
  box-shadow: var(--shadow-card);
}
.avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: 3px solid #fff;
  box-shadow: var(--shadow-soft);
  object-fit: cover;
  flex-shrink: 0;
}
.author-main h3 {
  margin: 0 0 6px;
  font-family: var(--font-head);
  font-size: 21px;
  font-weight: 700;
  color: var(--ink);
}
.author-line { margin: 0 0 4px; color: var(--forest); font-size: 13.5px; font-weight: 600; }
.version-line { margin: 0; color: var(--muted); font-size: 12.5px; }

/* 一键直达 */
.quick-links {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.link-btn {
  padding: 11px 8px;
  border: 1.5px solid var(--paper);
  border-radius: var(--r-md);
  background: var(--card);
  color: var(--forest);
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
  box-shadow: var(--shadow-soft);
  transition: all .15s ease;
}
.link-btn:hover { border-color: var(--sage); transform: translateY(-2px); }
.link-btn.star { color: #d48806; }
.star-hint { margin: -6px 0 0; text-align: center; color: var(--muted-faint); font-size: 12px; }

/* 自家表情走马灯 */
.sticker-strip {
  overflow: hidden;
  border-radius: var(--r-card);
  background: var(--card);
  border: 1.5px solid var(--paper);
  padding: 10px 0;
}
.strip-inner {
  display: flex;
  gap: 8px;
  width: max-content;
  animation: strip-scroll 30s linear infinite;
}
.strip-inner img { height: 56px; border-radius: var(--r-sm); }
@keyframes strip-scroll {
  from { transform: translateX(0); }
  50% { transform: translateX(-50%); }
  to { transform: translateX(0); }
}

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
