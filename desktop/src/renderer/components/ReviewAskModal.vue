<template>
  <transition name="fade">
    <div class="review-ask-mask" v-if="visible">
      <div class="review-ask">
        <button class="close" title="下次再说" @click="dismiss">✕</button>
        <img v-if="stickerUrl" class="mascot" :src="stickerUrl" alt="谢谢" />
        <h3>用得还顺手吗？</h3>
        <p class="sub">
          看到你已经发布了 <strong>{{ publishedCount }}</strong> 套表情，太棒了！
          <br />如果这个软件帮到了你——
        </p>
        <div class="btns">
          <button class="btn star" @click="go('star')">⭐ 给个 Star</button>
          <button class="btn" @click="go('feedback')">💬 说点建议</button>
          <button class="btn ghost" @click="dismiss">下次再说</button>
        </div>
        <p class="promise">（放心，15 天内不会再打扰你）</p>
      </div>
    </div>
  </transition>
</template>
<script setup>
import { ref, computed } from 'vue'
import { useEngineStore } from '../store/engine'

defineProps({ visible: Boolean })
const emit = defineEmits(['dismiss'])

const store = useEngineStore()
const publishedCount = computed(
  () => store.episodes.filter((e) => e.published).length)
const stickerUrl = ref('')

defineExpose({
  setSticker(url) { stickerUrl.value = url || '' },
})

function go(kind) {
  const url = kind === 'star'
    ? 'https://github.com/lyzbcy/sticker-maker'
    : 'https://github.com/lyzbcy/sticker-maker/discussions'
  if (window.api?.openExternal) window.api.openExternal(url)
  dismiss()
}
function dismiss() {
  emit('dismiss')
}
</script>
<style scoped>
.review-ask-mask {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(30, 40, 30, .35);
  display: flex; align-items: center; justify-content: center;
}
.review-ask {
  position: relative; width: 320px; padding: 26px 24px 18px;
  background: var(--card, #fff); border-radius: 18px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, .2);
  text-align: center;
}
.close {
  position: absolute; top: 10px; right: 12px;
  border: none; background: none; color: var(--muted, #999);
  font-size: 14px; cursor: pointer;
}
.mascot { height: 64px; margin-bottom: 6px; }
h3 { margin: 0 0 8px; font-size: 18px; color: var(--ink, #2e4a34); }
.sub { margin: 0 0 16px; font-size: 13.5px; color: var(--muted, #666); line-height: 1.7; }
.btns { display: flex; flex-direction: column; gap: 8px; }
.btn {
  padding: 10px; border-radius: 12px; border: 1.5px solid var(--paper, #eee);
  background: var(--card, #fff); font-weight: 700; font-size: 14px;
  cursor: pointer; color: var(--forest, #2e4a34);
}
.btn.star { background: #fffbe6; border-color: #ffe58f; color: #d48806; }
.btn.ghost { border: none; background: none; color: var(--muted-faint, #aaa); font-weight: 500; font-size: 12.5px; }
.promise { margin: 10px 0 0; font-size: 11.5px; color: var(--muted-faint, #bbb); }
.fade-enter-active, .fade-leave-active { transition: opacity .2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
