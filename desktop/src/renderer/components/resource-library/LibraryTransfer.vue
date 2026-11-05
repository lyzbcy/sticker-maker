<template>
<div class="resource-library-view">
<section v-if="library.storage_mode !== 'projects'" class="library-card">
      <div class="section-heading">
        <div>
          <h4>超级导出（旧资源库）</h4>
          <p class="hint">先扫描预览，再执行复制。备份不改变当前读写位置；迁移成功后才会切换。</p>
        </div>
      </div>
      <div class="purpose-row" role="radiogroup" aria-label="导出用途">
        <label class="purpose-option" :class="{ active: exportMode === 'backup' }">
          <input v-model="exportMode" data-test="mode-backup" type="radio" value="backup" />
          <span><strong>备份导出</strong><small>生成可导入副本，继续使用当前库</small></span>
        </label>
        <label class="purpose-option" :class="{ active: exportMode === 'migration' }">
          <input v-model="exportMode" data-test="mode-migration" type="radio" value="migration" />
          <span><strong>迁移并使用新位置</strong><small>校验完成后把当前库切到目标目录</small></span>
        </label>
      </div>
      <div class="form-row">
        <label class="field grow">
          <span>目标文件夹</span>
          <input v-model="exportTarget" data-test="export-target-path" type="text" readonly placeholder="请选择目标文件夹" />
        </label>
        <button class="btn secondary" data-test="export-target" type="button" @click="chooseExportTarget">选择文件夹…</button>
      </div>
      <p class="hint target-hint">建议选择全新的空文件夹作为目标；复制到已有文件的目录时，同名但内容不同的文件会被判为冲突。</p>
      <label class="check-line cleanup-line">
        <input v-model="cleanupOld" data-test="cleanup" type="checkbox" :disabled="exportMode !== 'migration'" />
        <span>迁移成功后清理旧位置中已确认复制的作品文件（默认关闭）</span>
      </label>
      <p v-if="conflictBlockCount" class="conflict-block-warning" data-test="migration-blocked-warning">
        ⚠ 当前存在 {{ conflictBlockCount }} 个版本冲突（作品或共享设置），生成迁移预览会被阻止。
        请先处理上方「版本冲突 / 设置版本冲突」卡片后再试；备份导出不受影响。
      </p>
      <div class="button-row transfer-actions">
        <button class="btn primary" data-test="preview-export" :disabled="previewing || !exportTarget" @click="previewExport">
          {{ previewing ? '扫描中…' : exportMode === 'migration' ? '生成迁移预览' : '生成备份预览' }}
        </button>
        <button class="btn primary" data-test="execute-export" :disabled="!canExecutePlan || executing"
                :title="executeDisabledReason || '按已确认的预览执行复制'" @click="executeExport">
          {{ executing ? '执行中…' : '执行已确认预览' }}
        </button>
      </div>
      <p v-if="executeDisabledReason" class="disabled-reason" data-test="execute-disabled-reason">
        暂不能执行：{{ executeDisabledReason }}
      </p>
      <div v-if="transferBusy" class="progress-line" data-test="transfer-progress" role="status" aria-live="polite">
        <div class="progress-track">
          <div class="progress-fill" :class="{ indeterminate: progressPercent == null }"
               :style="progressPercent != null ? { width: `${progressPercent}%` } : null"></div>
        </div>
        <p class="progress-text">
          {{ progressText }}<span v-if="elapsedSeconds > 0"> · 已用时 {{ elapsedSeconds }} 秒</span>
        </p>
      </div>
      <div v-if="executionResult" class="execution-result" :class="transferOutcomeClass(executionResult.state)" data-test="execution-result">
        <strong>{{ transferOutcomeLabel(executionResult.state) }}</strong>
        <span>已复制 {{ resultCount(executionResult.copied) }} 项</span>
        <span v-if="resultCount(executionResult.cleaned)">，已清理 {{ resultCount(executionResult.cleaned) }} 项</span>
        <span v-if="executionResult.missing?.length" class="missing-text">；仍缺失 {{ executionResult.missing.length }} 项</span>
        <span v-if="isTransferIncomplete(executionResult.state)" class="transfer-resume-hint">；仍可继续执行</span>
        <ul v-if="executionResult.errors?.length" class="missing-list">
          <li v-for="item in executionResult.errors" :key="missingLabel(item)">{{ missingLabel(item) }}</li>
        </ul>
      </div>
      <div v-if="plan" class="plan-box" data-test="preview-summary">
        <div class="plan-head">
          <strong>预览 {{ plan.plan_id }}</strong>
          <span>{{ plan.mode === 'migration' ? '迁移' : '备份' }} · {{ plan.target }}</span>
        </div>
        <p>将复制 {{ entryCount }} 项，共 {{ formatBytes(plan.bytes) }}。</p>
        <p v-if="plan.counts" data-test="preview-counts">
          作品 {{ plan.counts.works ?? plan.counts.available ?? plan.counts.total ?? '—' }} 项
          <template v-if="plan.counts.resources != null"> · 资源 {{ plan.counts.resources }} 项</template>
        </p>
        <div v-if="Array.isArray(plan.sources) && plan.sources.length" class="source-summary" data-test="preview-sources">
          <strong>来源与清理范围</strong>
          <ul>
            <li v-for="(source, index) in plan.sources" :key="`${sourcePathLabel(source)}-${index}`">
              {{ sourcePathLabel(source) }} · {{ sourceCleanupLabel(source, plan) }}
            </li>
          </ul>
          <p v-if="plan.cleanup" class="cleanup-warning">
            迁移成功后只清理已确认复制的文件；若源目录本身由 Syncthing 同步，删除会传播到其他设备。
          </p>
          <p v-if="plan.workspace_path || plan.cache_cleanup_path" class="cache-summary">
            工作缓存：{{ plan.workspace_path || plan.cache_cleanup_path }}（无需加入 Syncthing）
          </p>
        </div>
        <details v-if="plan.cleanup && plan.cache_cleanup?.files" class="source-summary" data-test="cache-cleanup-sources">
          <summary>同时清理已收录的旧副本：{{ plan.cache_cleanup.files }} 个文件，{{ formatBytes(plan.cache_cleanup.bytes) }}</summary>
          <p class="hint">只清理清单中的已收录文件；额外放入的未收录文件会保留。</p>
          <ul>
            <li v-for="source in plan.cache_cleanup.sources" :key="source.path">
              {{ source.path }} · {{ source.files }} 个已收录文件
            </li>
          </ul>
        </details>
        <p v-if="missing.length" class="missing-text">缺失 {{ missing.length }} 项，补齐后重新预览才能执行：</p>
        <ul v-if="missing.length" class="missing-list">
          <li v-for="item in missing" :key="missingLabel(item)">{{ missingLabel(item) }}</li>
        </ul>
        <p v-else class="success-text">清单已齐，可以执行。远端同步状态仍待 Syncthing 完成后核对。</p>
      </div>
    </section>
<section class="library-card">
      <div class="section-heading">
        <div>
          <h4>连接或复制导入</h4>
          <p class="hint">连接会持续发现 Syncthing 到达的新版本；复制导入只合并到当前库，不修改来源库。</p>
        </div>
      </div>
      <div class="form-row">
        <label class="field grow">
          <span>共享库 / 备份目录</span>
          <input v-model="sourcePath" data-test="source-path" type="text" readonly placeholder="请选择目录" />
        </label>
        <button class="btn secondary" data-test="choose-library" type="button" @click="chooseSourcePath">选择文件夹…</button>
      </div>
      <div class="button-row">
        <button class="btn primary" data-test="connect-library" :disabled="connecting || !sourcePath" @click="connectLibrary">
          {{ connecting ? '连接中…' : '连接共享资源库' }}
        </button>
        <button class="btn secondary" data-test="import-library" :disabled="importing || !sourcePath" @click="importLibrary">
          {{ importing ? '导入中…' : '复制导入到当前库' }}
        </button>
      </div>
      <p v-if="importTip" data-test="transfer-tip" class="transfer-tip" :class="transferTipClass">{{ importTip }}</p>
    </section>
<section v-if="tasks.length" class="library-card" data-test="transfer-tasks">
      <div class="section-heading">
        <div>
          <h4>未完成任务</h4>
          <p class="hint">应用会按 plan_id 从实际文件状态继续，重启后可以恢复。</p>
        </div>
      </div>
      <div v-for="task in tasks" :key="task.plan_id || task.id" class="task-row">
        <div>
          <strong>{{ task.plan_id || task.id }}</strong>
          <span>{{ task.state || task.status || '等待继续' }} · {{ task.target || '' }}</span>
        </div>
        <button class="btn secondary" :disabled="executing" @click="resumeTask(task)">继续执行</button>
      </div>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { library, exportMode, exportTarget, chooseExportTarget, cleanupOld, conflictBlockCount, previewing, previewExport, canExecutePlan, executing, executeDisabledReason, executeExport, transferBusy, progressPercent, progressText, elapsedSeconds, executionResult, transferOutcomeClass, transferOutcomeLabel, resultCount, isTransferIncomplete, missingLabel, plan, entryCount, formatBytes, sourcePathLabel, sourceCleanupLabel, missing, sourcePath, chooseSourcePath, connecting, connectLibrary, importing, importLibrary, importTip, transferTipClass, tasks, resumeTask } = useLibraryContext()
</script>
