<template>
<div class="resource-library-view">
<section class="library-card">
      <div class="section-heading">
        <div>
          <h4>作品记录（高级）</h4>
          <p class="hint">本机隐藏只影响本机列表；共享删除可恢复，并会同步删除版本。</p>
        </div>
      </div>
      <div class="form-row record-actions">
        <label class="field grow">
          <span>作品 work_id</span>
          <input v-model.trim="workInput" data-test="work-id" type="text" placeholder="粘贴要处理的 work_id" />
        </label>
        <button class="btn text-btn" data-test="hide-work" :disabled="!!recordAction || !workInput" @click="deleteWork('hide')">{{ recordAction === 'hide' ? '处理中…' : '仅本机隐藏' }}</button>
        <button class="btn danger" data-test="delete-work" :disabled="!!recordAction || !workInput" @click="deleteWork('delete')">{{ recordAction === 'delete' ? '处理中…' : '共享删除（会同步）' }}</button>
        <button class="btn secondary" data-test="restore-work" :disabled="!!recordAction || !workInput" @click="deleteWork('restore')">{{ recordAction === 'restore' ? '处理中…' : '恢复删除作品' }}</button>
      </div>
      <div v-if="deletedWorks.length" class="deleted-list">
        <span>已删除记录：</span>
        <button v-for="work in deletedWorks" :key="work.work_id" class="deleted-chip" @click="workInput = work.work_id">
          {{ work.album_name || work.work_id }}
        </button>
      </div>
      <div v-if="hiddenWorks.length" class="deleted-list hidden-list" data-test="hidden-works">
        <span>本机隐藏记录：</span>
        <button v-for="work in hiddenWorks" :key="work.work_id" class="deleted-chip" :disabled="!!recordAction" @click="unhideWork(work)">
          取消隐藏 {{ work.album_name || work.work_id }}
        </button>
      </div>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { workInput, recordAction, deleteWork, deletedWorks, hiddenWorks, unhideWork } = useLibraryContext()
</script>
