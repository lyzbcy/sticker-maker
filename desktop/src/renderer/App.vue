<template>
  <div class="app">
    <div v-if="store.phase === 'launch'" class="center">
      <div class="launch-pill">启动中…</div>
    </div>
    <Wizard v-else-if="store.phase === 'wizard'" class="page-fade" />
    <MainScreen v-else-if="store.phase === 'main'" class="page-fade" />
    <SettingsPanel v-else-if="store.phase === 'settings'" class="page-fade" />
    <AboutPanel v-else-if="store.phase === 'about'" class="page-fade" @back="store.phase = 'main'" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useEngineStore } from './store/engine'
import Wizard from './components/Wizard.vue'
import MainScreen from './components/MainScreen.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import AboutPanel from './components/AboutPanel.vue'

const store = useEngineStore()
onMounted(() => store.init())
</script>

<style>
/* ============ 设计令牌（捞鱼手作风） ============ */
:root {
  /* 底色 / 纸面 */
  --bg-cream: #FAF6EB;        /* 页面奶油底 */
  --paper: #F3EDDD;           /* 卡片纸面 */
  --card: #FFFFFF;            /* 纯白卡片 */
  --ink: #1A2018;             /* 主文字（偏暖近黑） */

  /* 主色（森林绿 IP 色） */
  --forest: #1E3A24;
  --forest-hover: #2A4D33;

  /* 中性辅助色（暖灰，从 ink 派生，保持奶油底协调） */
  --white: #FFFFFF;
  --muted: #6f7263;       /* 次要正文 */
  --muted-soft: #8a8d80;  /* 提示/meta */
  --muted-faint: #b0b2a8; /* 占位/最弱 */
  --line: #c8cabd;        /* 细线边框 */
  --brick-ink: #7a4632;   /* 红卡内文字 */
  --track-off: #d4d6cb;   /* 开关 off 轨道 */

  /* 记号 / 状态色 */
  --marker: #F5E08A;          /* 高亮 / 选中 */
  --sage: #AFCDA8;            /* 鼠尾草绿：成功 / active */
  --sky: #BCD8EE;             /* 天蓝点缀 */
  --brick: #B5482A;           /* 危险 */
  --correct: #2F7D46;         /* 成功 */

  /* 糖果点缀（只做小面积） */
  --candy-pink: #FFB7D5;
  --candy-blue: #B7E5FF;
  --candy-yellow: #FFE5A0;
  --candy-purple: #D5B7FF;
  --candy-mint: #B7FFD5;

  /* 柔光阴影（带颜色，不是死灰） */
  --shadow-card: 0 8px 24px rgba(30, 58, 36, .08);
  --shadow-card-hover: 0 12px 32px rgba(30, 58, 36, .14);
  --shadow-btn: 0 8px 20px rgba(30, 58, 36, .22);
  --shadow-soft: 0 4px 12px rgba(30, 58, 36, .06);

  /* 三色斜渐变（一键投递招牌） */
  --hero-gradient: linear-gradient(125deg, #fff3e7 0%, #ffeef2 45%, #e9f7ef 100%);

  /* 圆角 */
  --r-card: 22px;
  --r-lg: 20px;
  --r-md: 14px;
  --r-sm: 10px;
  --r-pill: 999px;

  /* 字体 */
  --font-display: "Archivo Black", "Noto Sans SC", "PingFang SC", sans-serif;
  --font-head: "Poppins", "Noto Sans SC", "PingFang SC", sans-serif;
  --font-body: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
  --font-fun: "ZCOOL KuaiLe", "Noto Sans SC", "PingFang SC", sans-serif;
}

/* ============ Body 重置 ============ */
body {
  margin: 0;
  font-family: var(--font-body);
  background: var(--bg-cream);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* { box-sizing: border-box; }

.app { min-height: 100vh; }

.center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}

.launch-pill {
  padding: 14px 28px;
  border-radius: var(--r-pill);
  background: var(--card);
  box-shadow: var(--shadow-card);
  color: var(--forest);
  font-weight: 600;
  font-size: 14px;
}

/* 页面切换淡入 */
.page-fade { animation: pageFadeIn .35s ease both; }
@keyframes pageFadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 全局滚动条（奶油风） */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--sage);
  border-radius: var(--r-pill);
  border: 3px solid var(--bg-cream);
}
::-webkit-scrollbar-thumb:hover { background: var(--forest-hover); }
</style>
