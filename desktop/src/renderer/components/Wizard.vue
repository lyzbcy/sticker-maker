<template>
  <div class="wizard">
    <div class="progress-dots">
      <span v-for="i in 5" :key="i" :class="{ active: i === step + 1, done: i <= step }">●</span>
    </div>
    <div class="step-title">步骤 {{ step + 1 }}/5：{{ stepNames[step] }}</div>
    <div class="step-body">
      <component :is="steps[step]" />
    </div>
    <div class="nav">
      <button v-if="step > 0" @click="step--" class="btn-secondary">上一步</button>
      <button v-if="step < 4" :disabled="!canNext" @click="step++">下一步</button>
      <button v-else @click="finish" class="btn-finish">完成</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useEngineStore } from '../store/engine'
import WizardStepCodex from './WizardStepCodex.vue'
import WizardStepBase from './WizardStepBase.vue'
import WizardStepMode from './WizardStepMode.vue'
import WizardStepChar from './WizardStepChar.vue'
import WizardStepPref from './WizardStepPref.vue'

const store = useEngineStore()
const step = ref(0)
const steps = [WizardStepCodex, WizardStepBase, WizardStepMode, WizardStepChar, WizardStepPref]
const stepNames = ['检测 codex', 'base 图管理', '模式概率', '角色概率', '生图偏好']

const canNext = computed(() => {
  if (step.value === 0) return store.codexStatus && store.codexStatus.image_ready
  return true
})

function finish() {
  store.savePrefs(store.prefs)
}
</script>

<style scoped>
.wizard { max-width: 640px; margin: 0 auto; padding: 30px 20px; }
.progress-dots { text-align: center; margin-bottom: 20px; }
.progress-dots span { margin: 0 6px; color: #ddd; font-size: 14px; }
.progress-dots .active { color: #4a90d9; }
.progress-dots .done { color: #7ac67d; }
.step-title { font-size: 18px; font-weight: 600; margin-bottom: 20px; }
.step-body { min-height: 240px; background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.nav { display: flex; justify-content: space-between; margin-top: 20px; }
button { padding: 8px 20px; border: none; border-radius: 6px; background: #4a90d9; color: #fff; cursor: pointer; }
button:disabled { background: #ccc; cursor: not-allowed; }
.btn-secondary { background: #eee; color: #333; }
.btn-finish { background: #7ac67d; }
</style>
