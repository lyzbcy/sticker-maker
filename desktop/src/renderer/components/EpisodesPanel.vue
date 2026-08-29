<template>
  <div class="episodes">
    <header>
      <button class="back" @click="store.phase = 'main'">← 返回</button>
      <h2>全部作品</h2>
      <span class="count">{{ filtered.length }} 个</span>
      <button class="sync-btn" :disabled="syncing" @click="doSync">
        <span v-if="syncing" class="spin">◌</span>
        {{ syncing ? '同步中…' : '一键更新' }}
      </button>
    </header>

    <!-- 同步结果摘要 -->
    <div v-if="syncSummary" class="sync-summary">
      ✅ 已同步 {{ syncSummary.matched }} 个作品（{{ syncSummary.pages }} 页）
      <template v-if="(syncSummary.unmatched_platform || []).length">
        ；平台有 {{ (syncSummary.unmatched_platform || []).length }} 条未匹配记录
        （可能是脏数据，如时间戳名）：<span class="unmatched-names">{{
          syncSummary.unmatched_platform.map(u => u.name).join('、')
        }}</span>
      </template>
    </div>

    <!-- 系列筛选 -->
    <div class="filter-row">
      <button class="chip" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
      <button class="chip" :class="{ active: filter === 'none' }" @click="filter = 'none'">未编系列</button>
      <button v-for="s in store.seriesList" :key="s.id" class="chip"
              :class="{ active: filter === s.id }" @click="filter = s.id">
        {{ s.name }}
      </button>
      <button class="chip chip-add" @click="store.phase = 'settings'">+ 管理系列</button>
    </div>

    <!-- 微信表情平台风表格：一行一个作品 -->
    <table class="ep-table" v-if="filtered.length">
      <thead>
        <tr>
          <th class="col-work">作品</th>
          <th>下载次数</th>
          <th>发送次数</th>
          <th>赞赏金额</th>
          <th>状态</th>
          <th>最后更新</th>
          <th class="col-ops">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="ep in filtered" :key="ep.path" :class="{ incomplete: !ep.complete }"
            @click="openRow(ep)">
          <td class="col-work">
            <img v-if="ep.cover" class="thumb" :src="fileUrl(ep.cover)" alt="" @error="onThumbError" />
            <div v-else class="thumb thumb-empty">🧸</div>
            <div class="work-info">
              <p class="work-name">{{ ep.album_name || ep.name }}</p>
              <p class="work-sub">
                {{ ep.sticker_count }} 张
                <template v-if="ep.series_name"> · {{ ep.series_name }} #{{ ep.number }}</template>
              </p>
            </div>
          </td>
          <td class="num">{{ ep.platform_downloads ?? '-' }}</td>
          <td class="num">{{ ep.platform_sends ?? '-' }}</td>
          <td class="num">{{ ep.platform_tips ?? '-' }}</td>
          <td>
            <span class="status-badge" :class="statusClass(ep)">{{ statusText(ep) }}</span>
            <div v-if="statusClass(ep) === 'st-reject' && ep.platform_reject_reason"
                 class="reject-reason" :title="ep.platform_reject_reason">
              {{ ep.platform_reject_reason.slice(0, 26) }}{{ ep.platform_reject_reason.length > 26 ? '…' : '' }}
            </div>
          </td>
          <td class="date">{{ displayDate(ep) }}</td>
          <td class="col-ops" @click.stop>
            <button class="op-btn" title="查看详情" @click="openRow(ep)">详情</button>
            <button v-if="ep.complete" class="op-btn pub" :disabled="store.publishing"
                    @click="store.publishEpisode(ep.path)">
              {{ ep.published ? '再次提交' : '提交' }}
            </button>
            <template v-if="confirming === ep.path">
              <button class="op-btn del sure" @click="doDelete(ep)">确认删除</button>
              <button class="op-btn" @click="confirming = ''">取消</button>
            </template>
            <button v-else class="op-btn del" title="连同本地文件夹一起物理删除"
                    @click="confirming = ep.path">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">还没有作品，去生成一组吧 ✨</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useEngineStore } from '../store/engine'

const store = useEngineStore()
const filter = ref('all')
const syncing = ref(false)
const syncSummary = ref(null)
const confirming = ref('')

onMounted(() => {
  store.loadEpisodes()
  store.loadSeries()
})

const filtered = computed(() => {
  const list = store.episodes
  if (filter.value === 'all') return list
  if (filter.value === 'none') return list.filter(e => !e.series_id)
  return list.filter(e => e.series_id === filter.value)
})

function openRow(ep) {
  if (ep.complete) store.openEpisode(ep.path)
}

function fileUrl(path) {
  return window.api?.toFileUrl ? window.api.toFileUrl(path) : `file://${path}`
}
function onThumbError(e) { e.target.style.display = 'none' }

function statusText(ep) {
  if (ep.platform_status) return ep.platform_status
  if (!ep.complete) return '未完成'
  return ep.published ? '已提交(未同步)' : '未提交'
}
function statusClass(ep) {
  const s = ep.platform_status || (ep.published ? '已提交' : '未提交')
  if (s.includes('上架')) return 'st-live'
  if (s.includes('待审核')) return 'st-review'
  if (s.includes('未通过')) return 'st-reject'
  if (s.includes('已保存')) return 'st-saved'
  if (s.includes('未完成')) return 'st-incomplete'
  return 'st-local'
}
function displayDate(ep) {
  if (ep.platform_updated_at) return ep.platform_updated_at.slice(0, 10) + '（同步）'
  return (ep.created_at || '').slice(0, 10) || '-'
}

async function doSync() {
  syncing.value = true
  syncSummary.value = null
  store.pushActivity({ stage: '同步', message: '一键更新：正在从微信平台抓取作品状态…' })
  try {
    const res = await window.api.send('sync_platform_status')
    if (res && res.status === 'ok') {
      syncSummary.value = res.data
      await store.loadEpisodes()
    } else {
      store.pushActivity({ stage: '同步', message: '同步失败：' + (res?.errors?.[0]?.message || '未知原因') })
    }
  } finally {
    syncing.value = false
  }
}

async function doDelete(ep) {
  confirming.value = ''
  const res = await window.api.send('delete_episode', { episode_dir: ep.path })
  if (res && res.status === 'ok') {
    store.pushActivity({
      stage: '作品', 
      message: `已物理删除 ${ep.album_name || ep.name}` + (res.data.rolled_back ? `（${res.data.rolled_back}）` : ''),
    })
    await store.loadEpisodes()
  } else {
    store.pushActivity({ stage: '作品', message: '删除失败：' + (res?.errors?.[0]?.message || '未知原因') })
  }
}
</script>

<style scoped>
.episodes { padding: 32px; max-width: 980px; margin: 0 auto; }

header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.back {
  background: var(--card); border: 1.5px solid var(--paper); border-radius: var(--r-pill);
  padding: 8px 18px; color: var(--forest); cursor: pointer; font-weight: 600; font-size: 14px;
  box-shadow: var(--shadow-soft); transition: all .15s ease;
}
.back:hover { border-color: var(--sage); transform: translateX(-2px); }
h2 { margin: 0; font-family: var(--font-head); font-size: 22px; font-weight: 700; color: var(--ink); }
.count { color: var(--muted-soft); font-size: 13px; margin-right: auto; }

.sync-btn {
  padding: 9px 20px; border-radius: var(--r-pill); border: none; cursor: pointer;
  background: var(--forest); color: var(--white); font-weight: 700; font-size: 13px;
  box-shadow: var(--shadow-btn); transition: all .15s ease;
}
.sync-btn:hover:not(:disabled) { background: var(--forest-hover); }
.sync-btn:disabled { opacity: .65; cursor: wait; }
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.sync-summary {
  padding: 10px 16px; margin-bottom: 14px; border-radius: var(--r-md);
  background: rgba(175, 205, 168, .18); color: var(--forest); font-size: 12.5px; line-height: 1.7;
}
.unmatched-names { color: var(--brick); }

.filter-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
.chip {
  padding: 7px 16px; border-radius: var(--r-pill); border: 1.5px solid var(--paper);
  background: var(--card); color: var(--muted); font-size: 12.5px; font-weight: 600;
  cursor: pointer; transition: all .15s ease;
}
.chip:hover { border-color: var(--sage); }
.chip.active { background: var(--forest); color: var(--white); border-color: var(--forest); }
.chip-add { border-style: dashed; color: var(--muted-soft); }

/* ---- 表格（微信平台风） ---- */
.ep-table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  background: var(--card); border-radius: var(--r-lg); overflow: hidden;
  box-shadow: var(--shadow-card); border: 1.5px solid var(--paper);
  font-size: 13px;
}
.ep-table thead th {
  text-align: left; padding: 12px 14px; font-size: 12px; font-weight: 700;
  color: var(--muted); background: var(--bg-cream); border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.ep-table tbody td {
  padding: 10px 14px; border-bottom: 1px solid var(--paper);
  vertical-align: middle; white-space: nowrap;
}
.ep-table tbody tr { cursor: pointer; transition: background .12s ease; }
.ep-table tbody tr:hover { background: rgba(175, 205, 168, .1); }
.ep-table tbody tr:last-child td { border-bottom: none; }
tr.incomplete { opacity: .6; }

.col-work { min-width: 220px; }
.col-work .thumb {
  width: 44px; height: 44px; border-radius: var(--r-sm); object-fit: cover;
  background: var(--bg-cream); display: inline-flex; align-items: center;
  justify-content: center; vertical-align: middle; margin-right: 12px;
  box-shadow: var(--shadow-soft);
}
.thumb-empty { font-size: 22px; }
.work-info { display: inline-block; vertical-align: middle; max-width: 240px; }
.work-name {
  margin: 0; font-weight: 700; color: var(--ink); font-size: 13.5px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.work-sub { margin: 2px 0 0; color: var(--muted-soft); font-size: 11.5px; }

.num, .date { color: var(--muted); text-align: center; }
.col-ops { text-align: right; }

.status-badge {
  display: inline-block; padding: 3px 10px; border-radius: var(--r-pill);
  font-size: 11.5px; font-weight: 700;
}
.st-live { background: rgba(47, 125, 70, .14); color: var(--correct); }
.st-review { background: rgba(230, 162, 60, .16); color: #b8860b; }
.st-reject { background: rgba(181, 72, 42, .12); color: var(--brick); }
.reject-reason { font-size: 10px; color: var(--brick); opacity: .85; margin-top: 3px;
  max-width: 150px; cursor: help; line-height: 1.35; }
.st-saved { background: rgba(110, 112, 99, .14); color: var(--muted); }
.st-local { background: var(--marker); color: var(--ink); }
.st-incomplete { background: var(--paper); color: var(--muted-soft); }

.op-btn {
  padding: 5px 12px; margin-left: 6px; border-radius: var(--r-pill);
  border: 1px solid var(--line); background: var(--card); color: var(--forest);
  font-size: 11.5px; font-weight: 700; cursor: pointer; transition: all .12s ease;
}
.op-btn:hover { border-color: var(--sage); }
.op-btn.pub { border-color: var(--sage); color: var(--correct); }
.op-btn.del { color: var(--muted-soft); }
.op-btn.del:hover { color: var(--brick); border-color: var(--brick); }
.op-btn.del.sure { background: var(--brick); border-color: var(--brick); color: #fff; }
.op-btn:disabled { opacity: .5; cursor: wait; }

.empty { padding: 60px 0; text-align: center; color: var(--muted-soft); }
</style>
