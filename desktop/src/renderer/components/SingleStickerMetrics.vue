<template>
  <section class="single-metrics">
    <h3>单个表情发送排名</h3>
    <p>读取平台单图当天发送次数，不将整套发送量分摊到单图，也不是累计发送量。只比较同一抓取日、同一平台日期。</p>
    <details><summary>刷新平台单图报告（按需读取）</summary><div class="controls">
      <label>读取范围 <select v-model="target" :disabled="busy" aria-label="单图读取范围"><option value="all">全部当前已上架作品（分套读取）</option><option v-for="ep in eligible" :key="ep.platform_item_id" :value="ep.platform_item_id">{{ ep.album_name || ep.name }}</option></select></label>
      <button data-test="fetch-singles" :disabled="busy || !eligible.length" @click="refresh">{{ busy ? '正在抓取单图报告…' : '刷新单图发送数据' }}</button>
      <button v-if="busy" data-test="cancel-singles" :disabled="!commandId || cancelling" @click="cancel">取消（保留已完成）</button>
    </div></details>
    <p role="status">{{ message || '默认仅加载前20条和图片；翻页时再读取下一批，不自动抓取平台。' }}</p>
    <p>已缓存 {{ cache.cached_albums || 0 }}/{{ cache.scope_albums || 0 }} 套；筛选范围共 {{ cache.total || 0 }} 张。缺失报告不记为零，失败保留旧数据。</p>
    <div class="controls filters">
      <label>统计日期 <select :value="observation || cache.observation" aria-label="单图统计日期" @change="observation=$event.target.value"><option v-for="g in cache.groups || []" :key="g.key" :value="g.key">{{ g.label }}</option></select></label>
      <label>搜索含义 / 作品 <input v-model="query" aria-label="搜索表情" placeholder="输入关键词" /></label>
      <label>排序 <select v-model="sort" aria-label="单图排序"><option value="desc">发送最多</option><option value="asc">发送最少（含0）</option></select></label>
    </div>
    <div class="insights"><span>筛选内当天发送 <b>{{ num(cache.summary?.sends) }}</b></span><span>有发送 <b>{{ cache.summary?.nonzero || 0 }}</b> 张</span><span>零发送 <b>{{ cache.summary?.zero || 0 }}</b> 张</span></div>
    <nav class="controls" aria-label="单图排名分页"><button data-test="prev-single" :disabled="loading || page===1" @click="page--">上一页</button><span>第 {{ page }}/{{ pages }} 页 · 每页20条 · 共 {{ cache.total || 0 }} 张</span><button data-test="next-single" :disabled="loading || page>=pages" @click="page++">下一页</button><span v-if="loading">加载中…</span></nav>
    <div class="table"><table><thead><tr><th>排名</th><th>原图（点击放大）</th><th>表情含义 / 作品</th><th>当天发送</th><th>筛选内占比</th><th>抓取时间</th></tr></thead><tbody><tr v-for="(row,index) in cache.rows || []" :key="row.item_id+'-'+row.md5+'-'+row.data_time"><td>{{ (page-1)*20+index+1 }}</td><td><button v-if="row.image_path && !failed[row.image_path]" class="image-button" :aria-label="'查看原图 '+row.meaning" @click="preview=row"><img :src="fileUrl(row.image_path)" :alt="row.meaning || '表情原图'" width="88" height="88" loading="lazy" decoding="async" @error="failed[row.image_path]=true" /></button><small v-if="row.image_path && !failed[row.image_path]">{{ row.image_match==='md5' ? '平台字节一致' : '本地同含义原图' }}</small><span v-else class="muted">{{ row.image_path ? '原图加载失败' : '本地原图未精确匹配' }}</span></td><td><b>{{ row.meaning || '图片 '+row.md5.slice(-8) }}</b><p>{{ row.album_name }} · 序号 {{ row.index || '—' }}</p></td><td><strong>{{ num(row.sends) }}</strong></td><td><span>{{ ((row.share || 0)*100).toFixed(1) }}%</span><meter :value="row.share || 0" min="0" max="1" /></td><td>{{ row.captured_at }}</td></tr></tbody></table></div>
    <p v-if="!loading && !cache.rows?.length">当前筛选暂无单图报告。可调整筛选，或展开上方入口读取平台报告。</p>
    <p>原图限定当前平台作品：优先匹配 MD5；平台字节不同时，仅展示含义与文件名完全一致的本地原图并单独标注，不冒充平台原文件；未匹配时明确显示。平台日期未提供年份，统计可能延迟。</p>
    <div v-if="preview" class="overlay" role="dialog" aria-modal="true" aria-label="表情原图" tabindex="0" @click.self="preview=null" @keydown.esc="preview=null"><article><button autofocus @click="preview=null">关闭原图</button><img :src="fileUrl(preview.image_path)" :alt="preview.meaning" /><h3>{{ preview.meaning }}</h3><p>{{ preview.album_name }} · 当天发送 {{ num(preview.sends) }}</p></article></div>
  </section>
</template>
<script setup>
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useEngineStore } from '../store/engine'
import { albumMetrics } from '../utils/analytics'
const store=useEngineStore(),cache=shallowRef({rows:[]}),target=ref('all'),busy=ref(false),loading=ref(false),cancelling=ref(false),commandId=ref(''),message=ref(''),observation=ref(''),query=ref(''),sort=ref('desc'),page=ref(1),preview=ref(null),failed=ref({})
const eligible=computed(()=>albumMetrics(store.episodes).filter(ep=>ep.platform_item_id && ['已上架','已下架','强制下架','预约上架失败'].includes(ep.platform_status)))
const pages=computed(()=>Math.max(1,Math.ceil((cache.value.total || 0)/20)))
const num=n=>n==null?'—':n.toLocaleString('zh-CN')
const fileUrl=p=>window.api?.toFileUrl ? window.api.toFileUrl(p) : 'file:///'+String(p).replace(/\\/g,'/').split('/').map(encodeURIComponent).join('/')
let generation=0,timer,disposed=false,lastPage=1,restoring=false
async function loadCache(){
 const current=++generation;loading.value=true
 try{const r=await window.api.send('get_sticker_metrics',{paginated:true,offset:(page.value-1)*20,limit:20,observation:observation.value,query:query.value,sort:sort.value});if(current!==generation || disposed)return;if(r?.status!=='ok')throw Error(r?.errors?.[0]?.message||'读取单图缓存失败');cache.value=r.data || {rows:[]};lastPage=page.value}
 catch(e){if(current===generation){message.value=e.message;if(page.value!==lastPage){restoring=true;page.value=lastPage}}}finally{if(current===generation)loading.value=false}
}
function firstPage(){if(page.value===1)loadCache();else page.value=1}
watch([observation,sort],firstPage)
watch(query,()=>{clearTimeout(timer);generation++;loading.value=true;timer=setTimeout(firstPage,250)})
watch(page,()=>{if(restoring){restoring=false;return}loadCache()})
watch(()=>store.episodes.map(ep=>ep.platform_item_id||'').join('|'),()=>{target.value='all';page.value=1;preview.value=null;cache.value={rows:[]};loadCache()},{immediate:true})
const unsubscribe=window.api.onProgress?.(e=>{if(busy.value && e.stage==='single_metrics'){commandId.value=e.id;message.value=e.message}})
onUnmounted(()=>{disposed=true;generation++;clearTimeout(timer);unsubscribe?.()})
async function refresh(){
 if(busy.value)return
 busy.value=true;cancelling.value=false;commandId.value='';message.value='正在校验平台账号与作品身份…'
 try{const r=await window.api.send('sync_sticker_metrics',target.value==='all'?{paginated:true}:{item_ids:[target.value],paginated:true});if(disposed)return;if(r?.status!=='ok')throw Error(r?.errors?.[0]?.message||'读取单图报告失败');const d=r.data || {};message.value=`${d.cancelled?'已取消':'本轮结束'}：读取 ${d.updated||0}/${d.total||0} 套，失败 ${d.failures?.length||0} 套。失败保留旧数据。`;await loadCache()}
 catch(e){message.value=e.message}finally{busy.value=false;cancelling.value=false}
}
async function cancel(){cancelling.value=true;try{await window.api.stop(commandId.value)}catch(e){message.value=e.message;cancelling.value=false}}
</script>
<style scoped>
.single-metrics{margin-top:28px} p,.muted{color:var(--muted);line-height:1.6} .controls,.insights{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:14px 0}.insights{padding:18px;background:var(--card);border-radius:14px;gap:30px} select{max-width:min(360px,100%)}button,select,input{padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:inherit}button:disabled{opacity:.5}summary{cursor:pointer;padding:12px}.table{overflow:auto;max-height:650px}th{position:sticky;top:0;background:var(--bg-cream);z-index:1}table{border-collapse:collapse;width:100%}th,td{padding:12px;border-bottom:1px solid var(--line);text-align:left}td p{margin:5px 0}td:last-child{font-size:12px}.image-button{padding:3px;cursor:zoom-in}img{object-fit:contain;background:repeating-conic-gradient(#eee 0% 25%,#fff 0% 50%) 0/16px 16px;border-radius:8px}small{display:block;color:var(--muted);font-size:11px}meter{display:block;width:90px}.overlay{position:fixed;inset:0;z-index:100;background:#000a;display:grid;place-items:center}.overlay article{max-width:90vw;max-height:90vh;overflow:auto;padding:24px;background:var(--card);border-radius:20px}.overlay img{display:block;width:min(480px,70vw);height:min(480px,60vh);margin-top:15px}
</style>
