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
<ResourceLocationPanel :initial-status="library" @changed="refreshLibrary" />
<ProjectStoragePanel :direct="library.storage_mode === 'projects'" :migration-id="library.project_migration_id" :retired="library.project_old_copies_retired" @changed="refreshLibrary" />
<LibraryStatus />

<LibrarySettingsConflicts />
<LibraryAccount />
<LibraryTransfer />


<LibraryWorkConflicts />
<LibraryOperations />
<LibraryRecords />
<LibraryHandoff />

</div>
</template>
<script setup>
import { provide } from 'vue'
import ProjectStoragePanel from './ProjectStoragePanel.vue'
import ResourceLocationPanel from './ResourceLocationPanel.vue'
import { useResourceLibrary } from './resource-library/useResourceLibrary'
import { resourceLibraryKey } from './resource-library/context'
import './resource-library/views.css'
import LibraryStatus from './resource-library/LibraryStatus.vue'
import LibrarySettingsConflicts from './resource-library/LibrarySettingsConflicts.vue'
import LibraryAccount from './resource-library/LibraryAccount.vue'
import LibraryTransfer from './resource-library/LibraryTransfer.vue'
import LibraryWorkConflicts from './resource-library/LibraryWorkConflicts.vue'
import LibraryOperations from './resource-library/LibraryOperations.vue'
import LibraryRecords from './resource-library/LibraryRecords.vue'
import LibraryHandoff from './resource-library/LibraryHandoff.vue'
const model = useResourceLibrary()
provide(resourceLibraryKey, model)
const { library, errorMessage, offline, refreshLibrary } = model
</script>
<style scoped>
.resource-library { display: flex; flex-direction: column; gap: 16px; }
.library-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.eyebrow { margin: 0 0 3px; color: var(--muted-soft); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
h3 { margin: 0; color: var(--forest); font-family: var(--font-head); font-size: 19px; }
.subtitle { margin: 5px 0 0; color: var(--muted); font-size: 12px; line-height: 1.65; }
.connection-badge { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11.5px; white-space: nowrap; }
.connection-badge.connected { background: rgba(175, 205, 168, .32); color: var(--correct); }
.connection-badge.offline { background: rgba(230, 162, 60, .16); color: #9a6c13; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted-faint); }
.connected .status-dot { background: var(--correct); }
.offline .status-dot { background: #e6a23c; }
.library-error { display: flex; align-items: center; gap: 10px; margin: 0; padding: 10px 13px; border-radius: var(--r-md); background: rgba(181, 72, 42, .1); color: var(--brick); font-size: 12.5px; }
.error-dismiss { margin-left: auto; border: 0; background: none; color: inherit; cursor: pointer; font-size: 11px; text-decoration: underline; }
@media (max-width: 620px) { .library-header { flex-direction: column; } .connection-badge { align-self: flex-start; } }
</style>
