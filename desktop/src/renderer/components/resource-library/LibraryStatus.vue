<template>
<div class="resource-library-view">
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
          <dt>{{ library.storage_mode === 'projects' ? '存储方式' : '本机工作缓存' }}</dt>
          <dd data-test="workspace-path">{{ library.storage_mode === 'projects' ? '直接读写工程，无完整工作副本' : library.workspace_path || '未连接' }}</dd>
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
      <p v-if="library.connected" class="sync-note">{{ library.storage_mode === 'projects' ? '同步整个工程集合；同一工程请在一台电脑上编辑，完成同步后再切换。' : 'Syncthing 只需同步资源库目录，旁边的工作缓存无需同步。' }}</p>
      <div v-if="library.accounts?.length" class="account-list" data-test="library-accounts">
        <span>库内账号：</span>
        <span v-for="account in library.accounts" :key="account.account_id" class="account-chip">
          {{ account.account_label || account.account_id }}
        </span>
      </div>
    </section>
</div>
</template>
<script setup>
import { useLibraryContext } from './context'
const { offline, warnings, warningLabel, refreshing, refreshLibrary, library, openLibrary, counts } = useLibraryContext()
</script>
