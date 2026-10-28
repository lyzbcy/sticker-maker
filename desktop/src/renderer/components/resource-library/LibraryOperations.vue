<template>
<div class="resource-library-view">
<section v-if="unresolvedOperations.length" class="library-card operation-card" data-test="unresolved-operations">
      <div class="section-heading">
        <div>
          <h4>提交结果待核对</h4>
          <p class="hint">请先在平台确认结果，再记录本机判断；应用不会自动重试提交。</p>
        </div>
      </div>
      <article v-for="operation in unresolvedOperations" :key="operation.operation_id" class="operation-row">
        <div>
          <strong>{{ operation.album_name || operation.work_id || '平台提交' }}</strong>
          <span>{{ operation.operation_id }} · {{ operation.phase || '结果待核对' }}</span>
        </div>
        <div class="button-row">
          <button class="btn primary" :data-test="`reconcile-submitted-${operation.operation_id}`"
                  :disabled="reconcilingOperation === operation.operation_id"
                  @click="reconcileOperation(operation, 'submitted')">已确认提交成功</button>
          <button class="btn secondary" :data-test="`reconcile-not-submitted-${operation.operation_id}`"
                  :disabled="reconcilingOperation === operation.operation_id"
                  @click="reconcileOperation(operation, 'not_submitted')">已确认未提交</button>
        </div>
      </article>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { unresolvedOperations, reconcilingOperation, reconcileOperation } = useLibraryContext()
</script>
