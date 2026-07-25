<template>
  <div class="settings">
    <header>
      <button class="back" @click="back">← 返回</button>
      <h2>设置</h2>
    </header>
    <div class="settings-body">
      <div class="section">
        <h3 class="section-title">base 图管理</h3>
        <WizardStepBase />
      </div>
      <div class="section">
        <h3 class="section-title">模式概率</h3>
        <WizardStepMode />
      </div>
      <div class="section">
        <h3 class="section-title">角色概率</h3>
        <WizardStepChar />
      </div>
      <div class="section">
        <h3 class="section-title">生图偏好</h3>
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
.settings { padding: 32px; max-width: 720px; margin: 0 auto; }

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

.settings-body { display: flex; flex-direction: column; gap: 16px; }

/* 分区 sticker-card */
.section {
  background: var(--card);
  padding: 24px;
  border-radius: var(--r-card);
  border: 1.5px solid var(--paper);
  box-shadow: var(--shadow-card);
}
.section-title {
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1.5px dashed var(--paper);
  font-family: var(--font-head);
  font-size: 16px;
  font-weight: 700;
  color: var(--forest);
}

/* 保存按钮（sage 绿） */
.save {
  align-self: center;
  padding: 13px 44px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--sage);
  color: var(--forest);
  cursor: pointer;
  margin-top: 8px;
  font-family: var(--font-head);
  font-weight: 700;
  font-size: 15px;
  box-shadow: 0 8px 20px rgba(175, 205, 168, .5);
  transition: all .15s ease;
}
.save:hover { transform: translateY(-1px); filter: brightness(1.03); }
.save:active { transform: translateY(1px); }
</style>
