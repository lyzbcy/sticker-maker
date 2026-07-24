<template>
  <div class="settings">
    <header>
      <button class="back" @click="back">← 返回</button>
      <h2>设置</h2>
    </header>
    <div class="settings-body">
      <div class="section">
        <h3>base 图管理</h3>
        <WizardStepBase />
      </div>
      <div class="section">
        <h3>模式概率</h3>
        <WizardStepMode />
      </div>
      <div class="section">
        <h3>角色概率</h3>
        <WizardStepChar />
      </div>
      <div class="section">
        <h3>生图偏好</h3>
        <WizardStepPref />
      </div>
      <button class="save" @click="save">保存</button>
    </div>
  </div>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
import WizardStepBase from './WizardStepBase.vue'
import WizardStepMode from './WizardStepMode.vue'
import WizardStepChar from './WizardStepChar.vue'
import WizardStepPref from './WizardStepPref.vue'

const store = useEngineStore()
async function save() {
  await store.savePrefs(store.prefs)
}
function back() {
  store.phase = 'main'
}
</script>
<style scoped>
.settings { padding: 24px; max-width: 720px; margin: 0 auto; }
header { display: flex; align-items: center; gap: 16px; }
.back { background: none; border: none; color: #4a90d9; cursor: pointer; font-size: 16px; }
.section { background: #fff; padding: 16px; border-radius: 8px; margin: 12px 0; }
.section h3 { margin-top: 0; }
.save { padding: 10px 30px; border: none; border-radius: 8px; background: #7ac67d; color: #fff; cursor: pointer; margin-top: 16px; }
</style>
