<template>
<div class="resource-library-view">
<section class="handoff-card">
      <div>
        <h4>准备切换电脑</h4>
        <p>保存当前批次和操作记录后，显示本机状态；请等待 Syncthing 完成同步。</p>
      </div>
      <button class="btn primary" data-test="handoff" :disabled="handingOff" @click="handoff">
        {{ handingOff ? '保存中…' : '准备切换电脑' }}
      </button>
    </section>
<p v-if="handoffMessage" class="handoff-message" data-test="handoff-message">{{ handoffMessage }}</p>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { handingOff, handoff, handoffMessage } = useLibraryContext()
</script>
