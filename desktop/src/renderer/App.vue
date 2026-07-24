<template>
  <div class="app">
    <div v-if="store.phase === 'launch'" class="center">
      <p>启动中…</p>
    </div>
    <Wizard v-else-if="store.phase === 'wizard'" />
    <MainScreen v-else-if="store.phase === 'main'" />
    <SettingsPanel v-else-if="store.phase === 'settings'" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useEngineStore } from './store/engine'
import Wizard from './components/Wizard.vue'
import MainScreen from './components/MainScreen.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const store = useEngineStore()
onMounted(() => store.init())
</script>

<style>
body { margin: 0; font-family: -apple-system, "PingFang SC", sans-serif; background: #fafafa; color: #333; }
.app { min-height: 100vh; }
.center { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
</style>
