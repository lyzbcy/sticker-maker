<template>
  <section class="analytics">
    <header><h2>数据看板</h2><button :disabled="busy" @click="refresh">{{ busy ? '同步中…' : '刷新平台数据' }}</button></header>
    <p role="status">{{ message || '展示最近一次平台观测；缺失数据以 — 表示，不计为零。' }}</p>
    <div class="cards"><article v-for="item in summaries" :key="item.key"><h3>{{ item.label }}</h3><strong>{{ display(item.value) }}</strong><p>{{ item.known }}/{{ rows.length }} 弹有数据</p></article></div>
    <article><h3>账号收益</h3><p v-if="store.income?.summary">累计赞赏 ¥{{ store.income.summary.total_tips }} · 累计热度 {{ store.income.summary.total_heat }} · 可提现 ¥{{ store.income.summary.withdrawable }}<br>成功读取：{{ store.income.fetched_at }}</p><p v-else>尚无账号收益数据</p><p role="status">{{ store.incomeError }}</p></article>
    <SingleStickerMetrics v-if="store.episodes.length" />
    <h3>整套表情排名</h3><label>排序 <select v-model="sort"><option value="sends">累计发送</option><option value="downloads">累计下载</option><option value="tips">赞赏金额</option></select></label>
    <div class="table"><table><thead><tr><th>原图 / 作品</th><th>累计发送</th><th>累计下载</th><th>赞赏金额</th><th>观测时间</th></tr></thead><tbody><tr v-for="ep in albumPage" :key="ep.work_id || ep.path || ep.name"><td><img v-if="ep.cover" :src="fileUrl(ep.cover)" :alt="ep.album_name || ep.name" width="64" height="64" loading="lazy" decoding="async" style="object-fit:contain;vertical-align:middle;margin-right:10px" />{{ ep.album_name || ep.name }}</td><td>{{ display(ep.sends) }}</td><td>{{ display(ep.downloads) }}</td><td>{{ display(ep.tips) }}</td><td>{{ ep.platform_updated_at || '—' }}</td></tr></tbody></table></div>
    <nav class="album-paging"><button :disabled="albumNumber===1" @click="albumNumber--">上一页</button> 第 {{ albumNumber }}/{{ albumPages }} 页 · 每页20套 <button :disabled="albumNumber>=albumPages" @click="albumNumber++">下一页</button></nav>
    <p v-if="!rows.length">暂无作品，请先连接资源位置。</p>
  </section>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useEngineStore } from '../store/engine'
import SingleStickerMetrics from './SingleStickerMetrics.vue'
import { albumMetrics, total, rank } from '../utils/analytics'
const store = useEngineStore(), busy = ref(false), message = ref(''), sort = ref('sends')
const rows = computed(() => albumMetrics(store.episodes))
const summaries = computed(() => [['sends','累计发送'],['downloads','累计下载'],['tips','累计赞赏（元）']].map(([key,label]) => ({ key,label,...total(rows.value,key) })))
const ranked = computed(() => rank(rows.value,sort.value))
const albumNumber=ref(1),albumPages=computed(()=>Math.max(1,Math.ceil(ranked.value.length/20))),albumPage=computed(()=>ranked.value.slice((albumNumber.value-1)*20,albumNumber.value*20))
watch(ranked,()=>{albumNumber.value=1})
const fileUrl=p=>window.api?.toFileUrl ? window.api.toFileUrl(p) : 'file:///'+String(p).replace(/\\/g,'/').split('/').map(encodeURIComponent).join('/')
const display = n => n == null ? '—' : n.toLocaleString('zh-CN')
onMounted(async () => { if(!store.episodes.length) await store.loadEpisodes(); if(!store.income) await store.loadIncome() })
async function refresh() {
  if (busy.value) return
  busy.value = true
  try {
    const r = await window.api.send('sync_platform_status', { fetch_reasons:false })
    if (r?.status !== 'ok') throw Error(r?.errors?.[0]?.message || '平台同步失败')
    store.acceptIncome(r.data?.income)
    await store.loadEpisodes()
    message.value = r.data?.cancelled ? '已取消，保留已完成数据' : r.data?.list_complete ? '平台作品数据已刷新' : '部分同步，请检查作品库同步结果'
  } catch(e) { message.value = e.message } finally { busy.value = false }
}
</script>
<style scoped>
.analytics { max-width:1200px; margin:auto; padding:24px; } header,.cards { display:flex; gap:16px; flex-wrap:wrap; align-items:center; } header { justify-content:space-between; } article { background:var(--card); padding:20px; border-radius:18px; margin:16px 0; flex:1; min-width:180px; } strong { font-size:28px; } button,select { padding:10px; border:1px solid var(--line); border-radius:12px; background:var(--card); } .table { overflow:auto; max-height:480px; } th { position:sticky; top:0; background:var(--bg-cream); } table { width:100%; border-collapse:collapse; } td,th { padding:12px; text-align:left; border-bottom:1px solid var(--line); }
</style>
