<template>
<div class="resource-library-view">
<section v-if="settingsConflicts.length" class="library-card settings-conflict-card" data-test="settings-conflicts">
      <div class="section-heading">
        <div>
          <h4>设置版本冲突</h4>
          <p class="hint">同一项共享设置存在多个设备版本；选择一个版本继续，其余分支会归档合并。设置只能选用版本，不支持另存为草稿。</p>
        </div>
      </div>
      <article v-for="conflict in settingsConflicts" :key="conflict.work_id" class="conflict-row">
        <div class="conflict-title">
          <strong>共享设置：{{ conflict.setting_type || conflict.logical_path || '未知类型' }}</strong>
          <span>{{ conflict.work_id }}</span>
        </div>
        <div v-for="head in conflict.heads || []" :key="head.revision_id" class="head-row">
          <span>版本 {{ String(head.revision_id || '').slice(0, 8) }} · {{ settingsHeadSummary(head) }}</span>
          <div class="button-row">
            <button class="btn secondary" :data-test="`choose-${head.revision_id}`"
                    :disabled="!!resolvingRevision" @click="resolveConflict(conflict, head, 'choose')">
              {{ resolvingRevision === head.revision_id ? '处理中…' : '选用此版本' }}
            </button>
          </div>
        </div>
        <p v-if="!(conflict.heads || []).length" class="hint">
          <span v-if="conflictDetail(conflict)">{{ conflictDetail(conflict) }} · </span>该冲突由本机诊断记录发现；点击上方「↻ 刷新资源」核对后，若仍冲突会显示各设备版本供选择。
        </p>
      </article>
      <p v-if="resolveMessage" class="resolve-message" data-test="resolve-message">{{ resolveMessage }}</p>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { settingsConflicts, settingsHeadSummary, resolvingRevision, resolveConflict, conflictDetail, resolveMessage } = useLibraryContext()
</script>
