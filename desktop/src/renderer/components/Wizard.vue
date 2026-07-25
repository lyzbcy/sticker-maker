<template>
  <div class="wizard">
    <div class="progress-dots">
      <span v-for="i in 5" :key="i" :class="{ active: i === step + 1, done: i <= step }">
        <i class="dot"></i>
      </span>
    </div>
    <div class="step-title">步骤 {{ step + 1 }}/5：{{ stepNames[step] }}</div>
    <div class="step-body">
      <component :is="steps[step]" />
    </div>
    <div class="nav">
      <button v-if="step > 0" @click="step--" class="btn-secondary">上一步</button>
      <span v-else></span>
      <button v-if="step < 4" :disabled="!canNext" @click="step++" class="btn-primary">下一步</button>
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
.wizard { max-width: 640px; margin: 0 auto; padding: 32px 20px; }

.progress-dots { display: flex; justify-content: center; gap: 10px; margin-bottom: 22px; }
.progress-dots span {
  display: grid;
  place-items: center;
  width: 14px;
  height: 14px;
}
.progress-dots .dot {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--paper);
  transition: all .2s ease;
}
.progress-dots .active .dot {
  width: 12px;
  height: 12px;
  background: var(--forest);
  box-shadow: 0 0 0 4px rgba(30, 58, 36, .12);
}
.progress-dots .done .dot { background: var(--candy-yellow); }

.step-title {
  font-family: var(--font-head);
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 18px;
  text-align: center;
}

.step-body {
  min-height: 240px;
  background: var(--card);
  border-radius: 24px;
  padding: 28px;
  box-shadow: var(--shadow-card);
  border: 1.5px solid var(--paper);
}

.nav { display: flex; justify-content: space-between; align-items: center; margin-top: 22px; }

button {
  font-family: var(--font-head);
  padding: 11px 28px;
  border: none;
  border-radius: var(--r-pill);
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  transition: all .15s ease;
}

.btn-primary {
  background: var(--forest);
  color: var(--white);
  box-shadow: var(--shadow-btn);
}
.btn-primary:hover:not(:disabled) { background: var(--forest-hover); transform: translateY(-1px); }
.btn-primary:active:not(:disabled) { transform: translateY(1px); }
.btn-primary:disabled { background: var(--paper); color: var(--muted-faint); cursor: not-allowed; box-shadow: none; }

.btn-secondary {
  background: var(--card);
  color: var(--forest);
  border: 1.5px solid var(--paper);
  box-shadow: var(--shadow-soft);
}
.btn-secondary:hover { border-color: var(--sage); transform: translateY(-1px); }

.btn-finish {
  background: var(--sage);
  color: var(--forest);
  box-shadow: 0 8px 20px rgba(175, 205, 168, .5);
}
.btn-finish:hover { transform: translateY(-1px); filter: brightness(1.03); }
.btn-finish:active { transform: translateY(1px); }
</style>
