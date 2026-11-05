<template>
<div class="resource-library-view">
<section v-if="conflicts.length" class="library-card conflict-card" data-test="conflicts">
      <div class="section-heading">
        <div>
          <h4>版本冲突</h4>
          <p class="hint">保留所有分支；选择版本会创建合并版本，另存为草稿不会复制平台作品 ID。</p>
        </div>
      </div>
      <article v-for="conflict in conflicts" :key="conflict.work_id" class="conflict-row">
        <div class="conflict-title">
          <strong>{{ conflict.album_name || conflict.work_id }}</strong>
          <span>{{ conflict.work_id }}</span>
        </div>
        <div v-for="head in conflict.heads || []" :key="head.revision_id" class="head-row">
          <span>{{ head.metadata?.device_label || head.metadata?.device_id || '另一台电脑' }} · {{ head.revision_id }}</span>
          <div class="button-row">
            <button class="btn secondary" :data-test="`choose-${head.revision_id}`"
                    :disabled="!!resolvingRevision" @click="resolveConflict(conflict, head, 'choose')">
              {{ resolvingRevision === head.revision_id ? '处理中…' : '选用此版本' }}
            </button>
            <button class="btn text-btn" :data-test="`draft-${head.revision_id}`"
                    :disabled="!!resolvingRevision" @click="resolveConflict(conflict, head, 'draft')">另存为草稿</button>
          </div>
        </div>
      </article>
      <p v-if="resolveMessage" class="resolve-message" data-test="resolve-message">{{ resolveMessage }}</p>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { conflicts, resolvingRevision, resolveConflict, resolveMessage } = useLibraryContext()
</script>
