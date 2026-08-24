<template>
  <div class="result">
    <!-- 失败卡片（brick 红，柔和不刺眼） -->
    <div v-if="store.lastError" class="error-card">
      <div class="state-icon err">!</div>
      <div class="card-body">
        <h4 class="card-title">生成失败</h4>
        <p v-for="(e, i) in store.lastError" :key="i" class="err-line">{{ e.message || e.gate }}</p>
        <div class="actions">
          <button class="btn btn-primary" @click="store.runGenerate">重试</button>
        </div>
      </div>
    </div>

    <!-- 成功卡片（sage 绿 + 庆祝感） -->
    <div v-else-if="store.lastEpisode" class="success-card">
      <div class="celebrate">🎉</div>
      <h4 class="success-title">完成！</h4>
      <p class="success-meta">{{ store.lastEpisode.stickers }} 张表情已就绪</p>
      <p class="hint">目录：{{ store.lastEpisode.episode_dir }}</p>
      <div v-if="store.publishProgress" class="publish-progress">
        {{ store.publishProgress.message }}
      </div>
      <p v-if="store.publishResult?.success" class="publish-ok">已提交到微信表情开放平台。</p>
      <div class="actions">
        <button class="btn btn-ghost" @click="openFinder">在文件夹中显示</button>
        <button
          class="btn btn-publish"
          data-test="publish"
          :disabled="store.publishing"
          @click="publish"
        >
          {{ store.publishing ? '正在提交…' : '一键提交微信' }}
        </button>
        <button class="btn btn-primary" @click="store.runGenerate">再生成一组</button>
        <button class="btn btn-soft" @click="store.clearResult">回到主页</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { useEngineStore } from '../store/engine'
const store = useEngineStore()
async function openFinder() {
  if (store.lastEpisode?.episode_dir && window.api) {
    await window.api.send('open_in_finder', { path: store.lastEpisode.episode_dir })
  }
}
async function publish() {
  if (store.lastEpisode?.episode_dir) {
    await store.publishEpisode(store.lastEpisode.episode_dir)
  }
}
</script>
<style scoped>
.result { padding: 8px 0; }

/* ============ 失败卡片 ============ */
.error-card {
  display: flex;
  gap: 14px;
  padding: 22px;
  background: rgba(181, 72, 42, .10);
  border: 1.5px solid rgba(181, 72, 42, .35);
  border-radius: var(--r-card);
}
.state-icon {
  flex-shrink: 0;
  width: 40px; height: 40px;
  display: grid; place-items: center;
  border-radius: 50%;
  font-weight: 700;
  font-size: 20px;
  color: var(--white);
}
.state-icon.err { background: var(--brick); }
.card-body { flex: 1; min-width: 0; }
.card-title {
  margin: 4px 0 8px;
  font-family: var(--font-head);
  font-size: 18px;
  font-weight: 700;
  color: var(--brick);
}
.err-line {
  margin: 4px 0;
  font-size: 13px;
  color: var(--brick-ink);
  word-break: break-word;
}

/* ============ 成功卡片（庆祝） ============ */
.success-card {
  padding: 32px;
  background: rgba(175, 205, 168, .28);
  border: 1.5px solid var(--sage);
  border-radius: var(--r-card);
  text-align: center;
}
.celebrate { font-size: 44px; margin-bottom: 6px; }
.success-title {
  margin: 0;
  font-family: var(--font-fun);
  font-size: 30px;
  font-weight: 700;
  color: var(--forest);
}
.success-meta {
  margin: 6px 0 12px;
  font-size: 15px;
  color: var(--forest);
  font-weight: 600;
}
.hint {
  color: var(--muted);
  font-size: 12px;
  word-break: break-all;
  margin: 0 0 18px;
  padding: 0 8px;
}
.publish-progress { color: var(--forest); font-size: 13px; font-weight: 600; }
.publish-ok { color: var(--correct); font-size: 13px; font-weight: 700; }

/* ============ 按钮（胶囊） ============ */
.actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
  justify-content: center;
}
.btn {
  padding: 11px 22px;
  border: none;
  border-radius: var(--r-pill);
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  transition: all .15s ease;
  font-family: var(--font-head);
}
.btn-primary {
  background: var(--forest);
  color: var(--white);
  box-shadow: var(--shadow-btn);
}
.btn-primary:hover { background: var(--forest-hover); transform: translateY(-1px); }
.btn-primary:active { transform: translateY(1px); }
.btn:disabled { opacity: .55; cursor: wait; transform: none; }
.btn-publish {
  background: var(--brick);
  color: var(--white);
  box-shadow: 0 8px 20px rgba(181, 72, 42, .22);
}
.btn-publish:hover:not(:disabled) { filter: brightness(1.06); transform: translateY(-1px); }

.btn-ghost {
  background: var(--card);
  color: var(--forest);
  border: 1.5px solid var(--sage);
}
.btn-ghost:hover { background: var(--sage); transform: translateY(-1px); }

.btn-soft {
  background: var(--card);
  color: var(--muted);
  border: 1.5px solid var(--paper);
}
.btn-soft:hover { background: var(--paper); color: var(--ink); transform: translateY(-1px); }
</style>
