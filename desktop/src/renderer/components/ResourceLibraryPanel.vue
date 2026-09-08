<template>
  <div class="resource-library" data-test="resource-library">
    <header class="library-header">
      <div>
        <p class="eyebrow">Syncthing 资源副本</p>
        <h3>账号与资源库</h3>
        <p class="subtitle">
          作品、素材和版本保存在共享目录；登录态与设备配置仍留在本机。
        </p>
      </div>
      <span class="connection-badge" :class="{ connected: library.connected && !offline, offline }">
        <span class="status-dot"></span>
        {{ offline ? '共享库离线' : library.connected ? '已连接本机库' : '尚未连接共享库' }}
      </span>
    </header>

    <p v-if="errorMessage" class="library-error" data-test="library-error" role="alert">
      {{ errorMessage }}
      <button class="error-dismiss" type="button" @click="errorMessage = ''">知道了</button>
    </p>

    <section v-if="offline || warnings.length" class="library-card status-alert" data-test="library-alert">
      <div class="section-heading">
        <div>
          <h4>{{ offline ? '共享库离线' : '资源库提醒' }}</h4>
          <p v-if="offline" class="hint">当前不会创建新的空库；请检查 Syncthing 配对、共享目录和文件权限后再刷新。</p>
        </div>
      </div>
      <ul v-if="warnings.length" class="status-list">
        <li v-for="(warning, index) in warnings" :key="`${warningLabel(warning)}-${index}`">{{ warningLabel(warning) }}</li>
      </ul>
    </section>

    <section class="library-card status-card">
      <div class="section-heading">
        <div>
          <h4>当前库状态</h4>
          <p class="hint">远端是否已经同步完成需要以 Syncthing 和文件校验结果为准。</p>
        </div>
        <div class="button-row">
          <button class="btn secondary" data-test="refresh-library" :disabled="refreshing" @click="refreshLibrary">
            {{ refreshing ? '刷新中…' : '↻ 刷新资源' }}
          </button>
          <button class="btn secondary" data-test="open-library" :disabled="!library.root" @click="openLibrary">
            打开目录
          </button>
        </div>
      </div>
      <dl class="status-grid">
        <div>
          <dt>库位置</dt>
          <dd data-test="library-root">{{ library.root || '未连接' }}</dd>
        </div>
        <div>
          <dt>本机工作缓存</dt>
          <dd data-test="workspace-path">{{ library.workspace_path || '未连接' }}</dd>
        </div>
        <div>
          <dt>库 ID</dt>
          <dd>{{ library.library_id || '—' }}</dd>
        </div>
        <div>
          <dt>当前账号</dt>
          <dd>{{ library.account_label || library.account_id || '待绑定' }}</dd>
        </div>
        <div>
          <dt>作品 / 资源</dt>
          <dd>
            {{ counts.available }} 可用 · {{ counts.placeholder }} 占位 ·
            {{ counts.pending }} 待同步 · {{ counts.conflict }} 冲突 · {{ counts.deleted }} 已删除
          </dd>
        </div>
      </dl>
      <p v-if="library.connected" class="sync-note">本机已保存到共享目录，请等待 Syncthing 完成同步后再在另一台电脑接手。</p>
      <p v-if="library.connected" class="sync-note">Syncthing 只需同步资源库目录，旁边的工作缓存无需同步。</p>
      <div v-if="library.accounts?.length" class="account-list" data-test="library-accounts">
        <span>库内账号：</span>
        <span v-for="account in library.accounts" :key="account.account_id" class="account-chip">
          {{ account.account_label || account.account_id }}
        </span>
      </div>
    </section>

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
        <p v-if="resolveMessage" class="resolve-message" data-test="resolve-message">{{ resolveMessage }}</p>
      </article>
    </section>

    <section class="library-card">
      <div class="section-heading">
        <div>
          <h4>绑定微信账号</h4>
          <p class="hint">绑定会校验平台登录账号，不保存密码或 Cookie。必须与发布设置中的登录账号保持一致；旧作品需要你明确确认归属。</p>
        </div>
      </div>
      <div class="form-row account-row">
        <label class="field grow">
          <span>平台登录账号</span>
          <input v-model.trim="accountInput" data-test="account-id" type="text" placeholder="与发布设置中的登录账号保持一致" />
        </label>
        <label class="check-line legacy-check">
          <input v-model="confirmLegacy" data-test="legacy-confirm" type="checkbox" />
          <span>我确认待绑定的旧作品属于这个账号</span>
        </label>
        <button class="btn primary" data-test="bind-account" :disabled="binding || !accountInput || !confirmLegacy" @click="bindAccount">
          {{ binding ? '绑定中…' : '确认绑定' }}
        </button>
      </div>
      <p v-if="accountTip" class="success-text">{{ accountTip }}</p>
    </section>

    <section class="library-card">
      <div class="section-heading">
        <div>
          <h4>超级导出</h4>
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
                    :disabled="!!resolvingRevision" @click="resolveConflict(conflict, head, 'choose')">选用此版本</button>
            <button class="btn text-btn" :data-test="`draft-${head.revision_id}`"
                    :disabled="!!resolvingRevision" @click="resolveConflict(conflict, head, 'draft')">另存为草稿</button>
          </div>
        </div>
        <p v-if="resolveMessage" class="resolve-message" data-test="resolve-message">{{ resolveMessage }}</p>
      </article>
    </section>

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

    <section class="library-card">
      <div class="section-heading">
        <div>
          <h4>作品记录</h4>
          <p class="hint">本机隐藏只影响本机列表；共享删除可恢复，并会同步删除版本。</p>
        </div>
      </div>
      <div class="form-row record-actions">
        <label class="field grow">
          <span>作品 work_id</span>
          <input v-model.trim="workInput" data-test="work-id" type="text" placeholder="粘贴要处理的 work_id" />
        </label>
        <button class="btn text-btn" data-test="hide-work" :disabled="!workInput" @click="deleteWork('hide')">本机隐藏</button>
        <button class="btn danger" data-test="delete-work" :disabled="!workInput" @click="deleteWork('delete')">共享删除</button>
        <button class="btn secondary" data-test="restore-work" :disabled="!workInput" @click="deleteWork('restore')">恢复删除作品</button>
      </div>
      <div v-if="deletedWorks.length" class="deleted-list">
        <span>已删除记录：</span>
        <button v-for="work in deletedWorks" :key="work.work_id" class="deleted-chip" @click="workInput = work.work_id">
          {{ work.album_name || work.work_id }}
        </button>
      </div>
      <div v-if="hiddenWorks.length" class="deleted-list hidden-list" data-test="hidden-works">
        <span>本机隐藏记录：</span>
        <button v-for="work in hiddenWorks" :key="work.work_id" class="deleted-chip" @click="unhideWork(work)">
          取消隐藏 {{ work.album_name || work.work_id }}
        </button>
      </div>
    </section>

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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const emptyStatus = () => ({
  connected: false, offline: false, root: '', library_id: '', account_id: '', account_label: '', accounts: [],
  workspace_path: '',
  counts: { available: 0, placeholder: 0, pending: 0, conflict: 0, deleted: 0 }, tasks: [], conflicts: [],
  warnings: [], settings_conflicts: [], hidden: [],
  unresolved_operations: [],
})

const library = ref(emptyStatus())
const errorMessage = ref('')
const accountInput = ref('')
const confirmLegacy = ref(false)
const accountTip = ref('')
const binding = ref(false)
const exportMode = ref('backup')
const exportTarget = ref('')
const cleanupOld = ref(false)
const previewing = ref(false)
const executing = ref(false)
const plan = ref(null)
const sourcePath = ref('')
const connecting = ref(false)
const importing = ref(false)
const importTip = ref('')
const workInput = ref('')
const handingOff = ref(false)
const handoffMessage = ref('')
const executionResult = ref(null)
const progressInfo = ref(null)
const progressStage = ref('')
const elapsedSeconds = ref(0)
let elapsedTimer = null
const transferTipClass = ref('transfer-success')
const refreshing = ref(false)
const mounted = ref(false)
let pollTimer = null
let pollInFlight = false

const counts = computed(() => ({
  available: Number(library.value.counts?.available || 0),
  placeholder: Number(library.value.counts?.placeholder || 0),
  pending: Number(library.value.counts?.pending || 0),
  conflict: Number(library.value.counts?.conflict || 0),
  deleted: Number(library.value.counts?.deleted || 0),
}))
const offline = computed(() => !!library.value.offline)
const warnings = computed(() => Array.isArray(library.value.warnings) ? library.value.warnings : [])
const settingsConflicts = computed(() => Array.isArray(library.value.settings_conflicts)
  ? library.value.settings_conflicts : [])
const tasks = computed(() => (Array.isArray(library.value.tasks) ? library.value.tasks : [])
  .filter(task => task?.state !== 'completed'))
const conflicts = computed(() => Array.isArray(library.value.conflicts) ? library.value.conflicts : [])
const unresolvedOperations = computed(() => Array.isArray(library.value.unresolved_operations)
  ? library.value.unresolved_operations : [])
const deletedWorks = computed(() => {
  if (Array.isArray(library.value.deleted_works)) return library.value.deleted_works
  if (Array.isArray(library.value.deleted)) return library.value.deleted
  return (Array.isArray(library.value.works) ? library.value.works : [])
    .filter(item => item.resource_state === 'deleted' || item.deleted)
})
const hiddenWorks = computed(() => {
  if (Array.isArray(library.value.hidden_works)) return library.value.hidden_works
  if (Array.isArray(library.value.hidden)) return library.value.hidden
  return []
})
const missing = computed(() => Array.isArray(plan.value?.missing) ? plan.value.missing : [])
const entryCount = computed(() => {
  if (Array.isArray(plan.value?.entries)) return plan.value.entries.length
  if (plan.value?.entries && typeof plan.value.entries === 'object') return Object.keys(plan.value.entries).length
  return 0
})
const canExecutePlan = computed(() => {
  const cleanup = exportMode.value === 'migration' && cleanupOld.value
  return !!plan.value?.plan_id && missing.value.length === 0 &&
    plan.value.mode === exportMode.value && Boolean(plan.value.cleanup) === cleanup
})
const executeDisabledReason = computed(() => {
  if (executing.value) return ''
  if (!plan.value?.plan_id) return '请先生成预览'
  if (missing.value.length) return `清单仍缺失 ${missing.value.length} 项，补齐后重新预览`
  const cleanup = exportMode.value === 'migration' && cleanupOld.value
  if (plan.value.mode !== exportMode.value) return '预览与当前导出用途不一致，请重新预览'
  if (Boolean(plan.value.cleanup) !== cleanup) return '清理开关与预览时不一致，请重新预览'
  return ''
})
const transferBusy = computed(() => previewing.value || executing.value)
const conflictBlockCount = computed(() => conflicts.value.length + settingsConflicts.value.length)
const progressPercent = computed(() => {
  if (previewing.value) return null
  const n = Number(progressInfo.value?.percent)
  return Number.isFinite(n) && n >= 0 ? Math.min(100, Math.round(n)) : null
})
const progressText = computed(() => {
  if (previewing.value) {
    const info = progressInfo.value
    if (info?.phase === 'scan' && Number.isFinite(info.scanned)) {
      return info.done
        ? `扫描完成：共检查 ${info.scanned} 个文件，正在汇总清单…`
        : `正在扫描资源库并校验文件哈希：已检查 ${info.scanned} 个文件…`
    }
    return progressStage.value || '正在扫描资源库并校验文件清单，文件多时可能需要几分钟…'
  }
  const info = progressInfo.value
  if (!info) return '正在校验清单并准备复制…'
  const label = info.phase === 'cleanup' ? '清理旧位置文件' : '复制到目标位置'
  return `${label}：${info.completed} / ${info.total} 项（${info.percent}%）`
})
function acceptProgress(ev) {
  if (!mounted.value || ev?.stage !== 'library' || !transferBusy.value) return
  if (previewing.value && typeof ev.message === 'string' && !ev.scanned) {
    progressStage.value = ev.message
  }
  let completed = Number(ev.completed)
  let total = Number(ev.total)
  let phase = ev.phase
  // 旧引擎把进度 dict 拍平成 message 字符串，从中兜底解析计数
  if (!(Number.isFinite(completed) && Number.isFinite(total) && total > 0)) {
    const match = typeof ev.message === 'string'
      ? ev.message.match(/'completed':\s*(\d+),?\s*'total':\s*(\d+)/) : null
    if (match) { completed = Number(match[1]); total = Number(match[2]) }
  }
  if (!phase && typeof ev.message === 'string') {
    if (ev.message.includes("'phase': 'cleanup'")) phase = 'cleanup'
    else if (ev.message.includes("'phase': 'scan'")) phase = 'scan'
  }
  if (Number.isFinite(completed) && Number.isFinite(total) && total > 0) {
    progressInfo.value = {
      phase: phase || 'copy',
      completed,
      total,
      percent: Math.min(100, Math.round((completed / total) * 100)),
    }
    return
  }
  const scanned = Number(ev.scanned)
  if (Number.isFinite(scanned)) {
    progressInfo.value = { phase: phase || 'scan', scanned, done: Boolean(ev.done) }
  }
}
watch(transferBusy, (busy) => {
  if (busy) {
    elapsedSeconds.value = 0
    progressInfo.value = null
    progressStage.value = ''
    if (!elapsedTimer) elapsedTimer = setInterval(() => { if (mounted.value) elapsedSeconds.value += 1 }, 1000)
  } else if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
})

function api() { return typeof window !== 'undefined' ? window.api : null }
function responseError(res, fallback = '操作失败') {
  return res?.errors?.[0]?.message || res?.raw?.errors?.[0]?.message || res?.error || res?.message || fallback
}
function exceptionError(err, fallback = '操作失败') {
  return err?.errors?.[0]?.message || err?.data?.errors?.[0]?.message || err?.message || fallback
}
async function send(cmd, args = {}) {
  if (!api()?.send) throw new Error('桌面引擎尚未连接')
  return api().send(cmd, JSON.parse(JSON.stringify(args)))
}
function setError(res, fallback) { errorMessage.value = responseError(res, fallback) }
function acceptStatus(data) {
  if (data && typeof data === 'object') library.value = { ...emptyStatus(), ...data, counts: { ...emptyStatus().counts, ...(data.counts || {}) } }
}

async function refreshStatus(options = {}) {
  if (pollInFlight) return null
  pollInFlight = true
  if (!options.quiet) refreshing.value = true
  try {
    const res = await send('library_status', {})
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      if (!options.quiet) errorMessage.value = ''
      return res.data
    }
    if (!options.quiet) setError(res, '读取资源库状态失败')
  } catch (err) {
    if (!options.quiet) errorMessage.value = exceptionError(err, '读取资源库状态失败')
  } finally {
    pollInFlight = false
    if (!options.quiet) refreshing.value = false
  }
  return null
}

async function refreshLibrary() {
  if (refreshing.value || pollInFlight) return
  pollInFlight = true
  refreshing.value = true
  try {
    const res = await send('library_refresh', {})
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      errorMessage.value = ''
    } else setError(res, '刷新资源库失败')
  } catch (err) { errorMessage.value = exceptionError(err, '刷新资源库失败') }
  finally { refreshing.value = false; pollInFlight = false }
}

function normalizePathResult(result) {
  if (typeof result === 'string') return result
  if (result && !result.canceled) return result.path || ''
  return ''
}
async function chooseExportTarget() {
  if (!api()?.selectDirectory) return
  exportTarget.value = normalizePathResult(await api().selectDirectory())
  invalidatePlan()
}
async function chooseSourcePath() {
  if (!api()?.selectDirectory) return
  sourcePath.value = normalizePathResult(await api().selectDirectory())
}

async function bindAccount() {
  if (!accountInput.value || !confirmLegacy.value || binding.value) return
  binding.value = true
  accountTip.value = ''
  try {
    const res = await send('library_bind_account', { account: accountInput.value, confirm_legacy: true })
    if (res?.status === 'ok') {
      accountTip.value = '✓ 已绑定账号；旧作品会按资源库身份合并'
      await refreshStatus({ quiet: true })
    } else setError(res, '账号绑定失败')
  } catch (err) { errorMessage.value = exceptionError(err, '账号绑定失败') }
  finally { binding.value = false }
}

async function previewExport() {
  if (!exportTarget.value || previewing.value) return
  previewing.value = true
  plan.value = null
  executionResult.value = null
  try {
    const res = await send('library_preview', {
      target: exportTarget.value,
      mode: exportMode.value,
      cleanup: exportMode.value === 'migration' && cleanupOld.value,
    })
    if (res?.status === 'ok' && res.data) plan.value = res.data
    else setError(res, '生成导出预览失败')
  } catch (err) { errorMessage.value = exceptionError(err, '生成导出预览失败') }
  finally { previewing.value = false }
}

function invalidatePlan() {
  plan.value = null
  executionResult.value = null
  importTip.value = ''
}

watch(exportMode, (mode) => {
  if (mode !== 'migration') cleanupOld.value = false
  invalidatePlan()
})
watch(cleanupOld, invalidatePlan)

async function executeExport() {
  if (!canExecutePlan.value || executing.value) return
  executing.value = true
  try {
    const res = await send('library_execute', { plan_id: plan.value.plan_id })
    if (res?.status === 'ok') {
      executionResult.value = res.data || {}
      setTransferTip(`${transferOutcomePrefix(res.data?.state)} ${transferOutcomeStateText(res.data?.state)}：已复制 ${resultCount(res.data?.copied)} 项`, res.data?.state)
      await refreshStatus({ quiet: true })
    } else setError(res, '执行导出失败')
  } catch (err) { errorMessage.value = exceptionError(err, '执行导出失败') }
  finally { executing.value = false }
}
async function resumeTask(task) {
  const planId = task?.plan_id || task?.id
  if (!planId || executing.value) return
  executing.value = true
  try {
    const res = await send('library_execute', { plan_id: planId })
    if (res?.status === 'ok') {
      executionResult.value = res.data || {}
      setTransferTip(`${transferOutcomePrefix(res.data?.state)} 任务 ${planId} ${transferOutcomeStateText(res.data?.state)}（已复制 ${resultCount(res.data?.copied)} 项）`, res.data?.state)
      await refreshStatus({ quiet: true })
    } else setError(res, '恢复任务失败')
  } catch (err) { errorMessage.value = exceptionError(err, '恢复任务失败') }
  finally { executing.value = false }
}
async function connectLibrary() {
  if (!sourcePath.value || connecting.value) return
  connecting.value = true
  try {
    const res = await send('library_connect', { path: sourcePath.value })
    if (res?.status === 'ok') { acceptStatus(res.data); setTransferTip('✓ 已连接共享资源库') }
    else setError(res, '连接共享资源库失败')
  } catch (err) { errorMessage.value = exceptionError(err, '连接共享资源库失败') }
  finally { connecting.value = false }
}
async function importLibrary() {
  if (!sourcePath.value || importing.value) return
  importing.value = true
  try {
    const res = await send('library_import', { path: sourcePath.value })
    if (res?.status === 'ok') {
      acceptStatus(res.data)
      setTransferTip(`✓ 已导入 ${importedCount(res.data?.imported)} 项`)
    }
    else setError(res, '复制导入失败')
  } catch (err) { errorMessage.value = exceptionError(err, '复制导入失败') }
  finally { importing.value = false }
}
async function openLibrary() {
  if (library.value.root && api()?.send) await send('open_in_finder', { path: library.value.root })
}
const resolvingRevision = ref('')
const resolveMessage = ref('')
async function resolveConflict(conflict, head, action) {
  const revisionId = head?.revision_id
  if (!conflict?.work_id || !revisionId || resolvingRevision.value) return
  resolvingRevision.value = revisionId
  resolveMessage.value = ''
  try {
    const res = await send('library_resolve', { work_id: conflict.work_id, revision_id: revisionId, action })
    if (res?.status === 'ok') {
      resolveMessage.value = `✓ 已选用版本 ${String(revisionId).slice(0, 8)}，正在刷新资源库状态（可能需要十几秒）…`
      await refreshStatus({ quiet: true })
      // 竞态兜底：resolve 返回时若 8 秒轮询正在跑，上面的刷新会被跳过，
      // 稍后强制再拉一次，确保冲突卡片真正消失
      setTimeout(() => { if (mounted.value) refreshStatus({ quiet: true }) }, 1500)
    } else {
      setError(res, '处理版本冲突失败')
      resolveMessage.value = `✗ ${responseError(res, '处理版本冲突失败')}`
    }
  } catch (err) {
    errorMessage.value = exceptionError(err, '处理版本冲突失败')
    resolveMessage.value = `✗ ${exceptionError(err, '处理版本冲突失败')}`
  } finally { resolvingRevision.value = '' }
}
const reconcilingOperation = ref('')
async function reconcileOperation(operation, outcome) {
  const operationId = operation?.operation_id
  if (!operationId || reconcilingOperation.value) return
  reconcilingOperation.value = operationId
  try {
    const res = await send('library_reconcile', { operation_id: operationId, outcome })
    if (res?.status === 'ok') await refreshStatus({ quiet: true })
    else setError(res, '提交结果核对失败')
  } catch (err) { errorMessage.value = exceptionError(err, '提交结果核对失败') }
  finally { reconcilingOperation.value = '' }
}
async function deleteWork(action) {
  if (!workInput.value) return
  if (action === 'delete' && typeof window !== 'undefined' && !window.confirm('共享删除会创建可同步的删除版本，确认继续吗？')) return
  try {
    const res = await send('library_delete', { work_id: workInput.value, action })
    if (res?.status === 'ok') {
      setTransferTip(action === 'restore' ? '✓ 已请求恢复作品' : action === 'hide' ? '✓ 已在本机隐藏作品' : '✓ 已创建共享删除版本')
      await refreshStatus({ quiet: true })
    }
    else setError(res, '处理作品记录失败')
  } catch (err) { errorMessage.value = exceptionError(err, '处理作品记录失败') }
}
async function unhideWork(work) {
  const workId = work?.work_id
  if (!workId) return
  try {
    const res = await send('library_delete', { work_id: workId, action: 'unhide' })
    if (res?.status === 'ok') {
      setTransferTip('✓ 已取消本机隐藏')
      await refreshStatus({ quiet: true })
    } else setError(res, '取消本机隐藏失败')
  } catch (err) { errorMessage.value = exceptionError(err, '取消本机隐藏失败') }
}
async function handoff() {
  if (handingOff.value) return
  handingOff.value = true
  handoffMessage.value = ''
  try {
    const res = await send('library_handoff', {})
    if (res?.status === 'ok') handoffMessage.value = res.data?.message || '已保存到共享目录，请等待 Syncthing 完成同步。'
    else setError(res, '准备切换电脑失败')
  } catch (err) { errorMessage.value = exceptionError(err, '准备切换电脑失败') }
  finally { handingOff.value = false }
}
function missingLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.logical_path || item?.source_path || item?.path || item?.name || JSON.stringify(item)
}
function warningLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.message || item?.detail || item?.warning || item?.path || JSON.stringify(item)
}
function conflictLabel(item) {
  return typeof item === 'string'
    ? item
    : item?.message || item?.detail || item?.setting_type || item?.name || JSON.stringify(item)
}
// 设置冲突各版本的内容摘要：帮助用户分辨两台设备改了什么
function conflictDetail(item) {
  if (typeof item === 'string') return item
  return item?.message || item?.detail || ''
}
function settingsHeadSummary(head) {
  const payload = head?.metadata?.payload || {}
  const bits = []
  if (payload.sticker_price != null) bits.push(`价格 ${payload.sticker_price}`)
  if (payload.grid_size != null) bits.push(`宫格 ${payload.grid_size}`)
  if (payload.story_mode != null) bits.push(payload.story_mode ? '剧情模式' : '普通模式')
  if (payload.default_series_id) bits.push(`默认系列 ${String(payload.default_series_id).slice(0, 8)}`)
  if (payload.reference_lib_path) bits.push(`参考图库 ${payload.reference_lib_path}`)
  if (payload.transparent_default != null) bits.push(payload.transparent_default ? '默认透明底' : '默认白底')
  return bits.length ? bits.join(' · ') : '（无差异摘要，可按版本号选用）'
}
function sourcePathLabel(source) {
  return source?.path || source?.source_root || source?.source_path || source?.name || '来源目录待核对'
}
function sourceCleanupLabel(source, planData) {
  const cleanup = source?.cleanup ?? source?.cleanup_enabled ?? planData?.cleanup
  return cleanup ? '迁移后清理已确认复制文件' : '只复制，不清理源文件'
}
function resultCount(value) { return Array.isArray(value) ? value.length : Number(value || 0) }
function importedCount(value) {
  if (Array.isArray(value)) return value.length
  if (value && typeof value === 'object') {
    if (Array.isArray(value.copied)) return value.copied.length
    if (Array.isArray(value.imported)) return value.imported.length
    if (Number.isFinite(Number(value.count))) return Number(value.count)
  }
  return Number(value || 0)
}
function isTransferIncomplete(state) { return state && state !== 'completed' }
function transferOutcomeClass(state) {
  if (state === 'completed') return 'transfer-success'
  if (state === 'cleanup_partial' || state === 'incomplete') return 'transfer-warning'
  return 'transfer-error'
}
function transferOutcomePrefix(state) {
  if (state === 'completed') return '✓'
  if (state === 'cleanup_partial' || state === 'incomplete') return '⚠'
  return '✗'
}
function transferOutcomeStateText(state) {
  if (state === 'completed') return '已完成'
  if (state === 'cleanup_partial') return '复制完成，但清理未完成'
  if (state === 'incomplete') return '未完成'
  if (state === 'failed') return '失败'
  if (state === 'cancelled') return '已取消'
  return state || '状态待核对'
}
function transferOutcomeLabel(state) { return `${transferOutcomePrefix(state)} ${transferOutcomeStateText(state)}` }
function setTransferTip(message, state = 'completed') {
  importTip.value = message
  transferTipClass.value = transferOutcomeClass(state)
}
function formatBytes(value) {
  const n = Number(value || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

onMounted(async () => {
  mounted.value = true
  if (api()?.onProgress) api().onProgress(acceptProgress)
  await refreshStatus()
  if (!mounted.value) return
  pollTimer = setInterval(() => {
    // 扫描/执行期间暂停轮询：status 轮询与预览抢同一把引擎锁，
    // 撞车会让预览被"资源任务正在进行"秒拒
    if (mounted.value && !transferBusy.value) refreshStatus({ quiet: true })
  }, 8000)
})
onBeforeUnmount(() => {
  mounted.value = false
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = null
})
</script>

<style scoped>
.resource-library { display: flex; flex-direction: column; gap: 16px; }
.library-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.eyebrow { margin: 0 0 3px; color: var(--muted-soft); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
h3, h4 { margin: 0; color: var(--forest); font-family: var(--font-head); }
h3 { font-size: 19px; }
h4 { font-size: 15px; }
.subtitle, .hint { margin: 5px 0 0; color: var(--muted); font-size: 12px; line-height: 1.65; }
.connection-badge { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11.5px; white-space: nowrap; }
.connection-badge.connected { background: rgba(175, 205, 168, .32); color: var(--correct); }
.connection-badge.offline { background: rgba(230, 162, 60, .16); color: #9a6c13; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted-faint); }
.connected .status-dot { background: var(--correct); }
.offline .status-dot { background: #e6a23c; }
.library-card, .handoff-card { padding: 20px; border: 1.5px solid var(--paper); border-radius: var(--r-card); background: var(--card); box-shadow: var(--shadow-card); }
.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.button-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 0; }
.status-grid > div { min-width: 0; padding: 10px 12px; border-radius: var(--r-md); background: var(--bg-cream); }
dt { color: var(--muted-soft); font-size: 11px; }
dd { margin: 3px 0 0; color: var(--ink); font-size: 12.5px; word-break: break-word; }
.sync-note, .handoff-message { margin: 12px 0 0; color: var(--forest); font-size: 12px; line-height: 1.6; }
.account-list { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; color: var(--muted); font-size: 11px; }
.account-chip { padding: 3px 9px; border-radius: 999px; background: var(--paper); color: var(--forest); font-weight: 700; }
.library-error { display: flex; align-items: center; gap: 10px; margin: 0; padding: 10px 13px; border-radius: var(--r-md); background: rgba(181, 72, 42, .1); color: var(--brick); font-size: 12.5px; }
.error-dismiss { margin-left: auto; border: 0; background: none; color: inherit; cursor: pointer; font-size: 11px; text-decoration: underline; }
.status-alert { border-color: rgba(230, 162, 60, .42); background: rgba(230, 162, 60, .08); }
.status-alert .section-heading { margin-bottom: 0; }
.status-list { margin: 10px 0 0; padding-left: 20px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.status-list li + li { margin-top: 4px; }
.settings-conflict-card { border-color: rgba(181, 72, 42, .24); }
.form-row { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 6px; min-width: 190px; }
.field > span { color: var(--muted); font-size: 12px; font-weight: 600; }
.grow { flex: 1; }
input[type="text"] { width: 100%; padding: 9px 12px; border: 1.5px solid var(--paper); border-radius: var(--r-md); background: var(--bg-cream); color: var(--ink); font: inherit; font-size: 12.5px; }
input[type="text"]:focus { outline: none; border-color: var(--sage); }
.check-line { display: inline-flex; align-items: flex-start; gap: 8px; color: var(--muted); font-size: 12px; line-height: 1.5; cursor: pointer; }
.check-line input { margin-top: 2px; accent-color: var(--forest); }
.account-row { align-items: flex-end; }
.legacy-check { max-width: 250px; padding-bottom: 9px; }
.btn { border: 1.5px solid var(--forest); border-radius: var(--r-pill); padding: 8px 14px; background: var(--card); color: var(--forest); cursor: pointer; font: inherit; font-size: 12px; font-weight: 700; white-space: nowrap; }
.btn:hover:not(:disabled) { background: var(--forest); color: #fff; }
.btn.primary { background: var(--forest); color: #fff; box-shadow: var(--shadow-btn); }
.btn.primary:hover:not(:disabled) { background: var(--forest-hover); }
.btn.secondary { border-color: var(--line); color: var(--muted); }
.btn.text-btn { border-color: transparent; color: var(--forest); }
.btn.danger { border-color: rgba(181,72,42,.45); color: var(--brick); }
.btn.danger:hover:not(:disabled) { background: var(--brick); color: #fff; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.success-text { margin: 10px 0 0; color: var(--correct); font-size: 12px; font-weight: 600; }
.purpose-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.purpose-option { display: flex; gap: 9px; padding: 12px; border: 1.5px solid var(--paper); border-radius: var(--r-md); cursor: pointer; }
.purpose-option.active { border-color: var(--forest); background: rgba(175,205,168,.14); }
.purpose-option input { margin-top: 3px; accent-color: var(--forest); }
.purpose-option strong, .purpose-option small { display: block; }
.purpose-option strong { color: var(--ink); font-size: 12.5px; }
.purpose-option small { margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.5; }
.cleanup-line { margin-top: 12px; }
.conflict-block-warning { margin: 10px 0 0; padding: 9px 12px; border-radius: var(--r-md); background: rgba(181, 72, 42, .08); color: var(--brick); font-size: 12px; line-height: 1.6; }
.resolve-message { margin: 10px 0 0; color: var(--muted); font-size: 12px; font-weight: 600; }
.target-hint { margin: 8px 0 0; }
.transfer-actions { margin-top: 13px; }
.disabled-reason { margin: 8px 0 0; color: #9a6c13; font-size: 11.5px; line-height: 1.6; }
.progress-line { margin-top: 12px; }
.progress-track { height: 8px; border-radius: 999px; background: var(--paper); overflow: hidden; }
.progress-fill { height: 100%; border-radius: 999px; background: var(--forest); transition: width .25s ease; }
.progress-fill.indeterminate { width: 38%; animation: indeterminate-slide 1.1s ease-in-out infinite; }
.progress-text { margin: 7px 0 0; color: var(--muted); font-size: 11.5px; line-height: 1.6; }
@keyframes indeterminate-slide { 0% { margin-left: -38%; } 100% { margin-left: 100%; } }
.plan-box { margin-top: 14px; padding: 13px 15px; border-radius: var(--r-md); background: var(--bg-cream); border: 1.5px dashed var(--line); color: var(--muted); font-size: 12px; line-height: 1.6; }
.plan-box p { margin: 5px 0 0; }
.execution-result { margin-top: 12px; padding: 10px 13px; border-radius: var(--r-md); background: rgba(175,205,168,.16); color: var(--forest); font-size: 12px; }
.execution-result.transfer-warning, .transfer-tip.transfer-warning { background: rgba(230,162,60,.14); color: #9a6c13; }
.execution-result.transfer-error, .transfer-tip.transfer-error { background: rgba(181,72,42,.1); color: var(--brick); }
.transfer-tip { margin: 10px 0 0; font-size: 12px; font-weight: 600; }
.transfer-tip.transfer-success { color: var(--correct); }
.execution-result > span { margin-left: 8px; color: var(--muted); }
.execution-result .transfer-resume-hint { color: #9a6c13; font-weight: 700; }
.execution-result .missing-list { margin-bottom: 0; }
.plan-head { display: flex; justify-content: space-between; gap: 12px; color: var(--forest); font-size: 12px; }
.plan-head span { color: var(--muted); word-break: break-word; text-align: right; }
.source-summary { margin-top: 11px; padding: 10px 12px; border: 1px solid var(--paper); border-radius: var(--r-md); background: rgba(255, 255, 255, .42); color: var(--ink); }
.source-summary > strong { color: var(--forest); font-size: 12px; }
.source-summary ul { margin: 6px 0 0; padding-left: 19px; color: var(--muted); }
.source-summary li { overflow-wrap: anywhere; }
.cleanup-warning { color: #9a6c13; }
.cache-summary { overflow-wrap: anywhere; color: var(--muted-soft); }
.missing-text { color: var(--brick); font-weight: 700; }
.missing-list { margin: 5px 0 0; padding-left: 20px; color: var(--brick); }
.task-row, .conflict-row, .head-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 11px 0; border-top: 1px solid var(--paper); }
.operation-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 11px 0; border-top: 1px solid var(--paper); }
.operation-row strong, .operation-row span { display: block; }
.operation-row strong { color: var(--ink); font-size: 12.5px; }
.operation-row span { margin-top: 3px; color: var(--muted); font-size: 11px; word-break: break-word; }
.task-row:first-of-type, .conflict-row:first-of-type { border-top: 0; }
.task-row strong, .task-row span, .conflict-title strong, .conflict-title span, .head-row > span { display: block; }
.task-row strong, .conflict-title strong { color: var(--ink); font-size: 12.5px; }
.task-row span, .conflict-title span, .head-row > span { margin-top: 3px; color: var(--muted); font-size: 11px; word-break: break-word; }
.conflict-row { display: block; }
.head-row { padding-left: 10px; }
.record-actions { align-items: flex-end; }
.deleted-list { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; margin-top: 12px; color: var(--muted); font-size: 11px; }
.hidden-list { padding-top: 10px; border-top: 1px solid var(--paper); }
.deleted-chip { border: 1px solid var(--line); border-radius: 999px; padding: 4px 10px; background: var(--card); color: var(--muted); cursor: pointer; font-size: 11px; }
.handoff-card { display: flex; justify-content: space-between; align-items: center; gap: 16px; background: var(--hero-gradient); }
.handoff-card p { margin: 5px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
@media (max-width: 620px) {
  .library-header, .section-heading, .handoff-card { flex-direction: column; }
  .status-grid, .purpose-row { grid-template-columns: 1fr; }
  .connection-badge { align-self: flex-start; }
  .plan-head, .task-row, .head-row, .operation-row { align-items: flex-start; flex-direction: column; }
  .head-row .button-row { width: 100%; }
}
</style>
