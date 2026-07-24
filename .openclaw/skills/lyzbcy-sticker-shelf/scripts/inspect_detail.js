/**
 * inspect_detail.js — 「审核通过」单品详情页只读探测脚本
 *
 * 用途：自动登录 → 进首页 → 点第一个「审核通过」单曲行的「详情」
 *       (a[href="javascript:;"]) → 只读 dump 详情页 DOM 结构，
 *       为 shelf.js 主脚本固化「上架 / 日历 / 预约」的准确选择器。
 *
 * 🔴 安全保证：
 *   - 只读取、不点击「上架」「预约」，不改任何状态
 *   - 点「详情」是只读导航（不会上架/下架），属于必要前置
 *   - 全程不会上传文件、不会预约
 *
 * 用法：
 *   node inspect_detail.js            # 自动登录 + 进详情页 + dump DOM
 */

const path = require('path');
const fs = require('fs');
const { HOME_URL, sleep, loadCredentials, launchBrowser, ensureLogin } = require('./wechat-launch');

const OUT_FILE = path.join(__dirname, 'inspect_detail_result.json');

(async () => {
  console.log('=== 详情页只读探测脚本启动 ===');

  const creds = loadCredentials();
  console.log('账号:', creds.account || '(未配置)');

  const browser = await launchBrowser();
  const page = await browser.newPage();
  page.setDefaultTimeout(300000);

  try {
    // 1. 打开首页 + 登录
    console.log('📍 打开首页...');
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
        break;
      } catch (e) {
        console.log('  ⚠️ goto 失败 (' + (attempt + 1) + '): ' + e.message.split('\n')[0]);
        if (attempt < 2) { await sleep(3000); }
      }
    }

    const ok = await ensureLogin(page, creds);
    if (!ok) {
      console.error('❌ 登录失败，无法继续探测。');
      await browser.disconnect().catch(() => {});
      process.exit(1);
    }

    // 登录后若被重定向，回首页列表
    if (!page.url().includes('home/index') && !page.url().includes('home')) {
      console.log('📍 重新导航回首页列表...');
      await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    }
    await sleep(3000);

    // 记录点详情前的窗口数（判断详情是弹窗还是新 tab）
    const pagesBefore = (await browser.pages()).length;
    const urlBefore = page.url();
    console.log('📍 点详情前: URL=' + urlBefore + ' | 页签数=' + pagesBefore);

    // 2. 定位「审核通过」单曲行的「详情」a[href="javascript:;"]
    //    首页有两类详情：
    //      - 形象详情：a[href*="ip/detail"]
    //      - 单曲/单品详情：a[href="javascript:;"]  ← 我们要点这种
    //    且只在「审核通过」所在行附近找。
    const detailClicked = await page.evaluate(() => {
      const isVisible = (el) => {
        if (!el) return false;
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      };
      // 所有单曲行：tbody.table_body > tr.table_tr
      const rows = Array.from(document.querySelectorAll('tbody.table_body tr.table_tr'));
      for (const row of rows) {
        const txt = (row.innerText || '');
        // 该行必须是「审核通过」（排除已上架/审核中）
        if (!txt.includes('审核通过')) continue;
        // 找该行的「详情」单曲链接（href="javascript:;"）
        const link = row.querySelector('a[href="javascript:;"]');
        if (link && isVisible(link)) {
          // 返回行列定位信息 + 触发点击
          const r = link.getBoundingClientRect();
          link.click();
          return {
            ok: true,
            rowTextHead: txt.slice(0, 120).replace(/\s+/g, ' ').trim(),
            clickedLinkHref: link.getAttribute('href'),
          };
        }
      }
      return { ok: false };
    });

    if (!detailClicked.ok) {
      console.log('⚠️ 当前页未找到「审核通过」单曲行，尝试翻到下一页再找...');
      // 最多翻 3 页
      let found = false;
      for (let p = 0; p < 3 && !found; p++) {
        const nextBtn = await page.evaluate(() => {
          const a = Array.from(document.querySelectorAll('a.weui-desktop-pagination__nav, a'))
            .find(el => (el.innerText || '').trim() === '下一页' && el.getBoundingClientRect().width > 0);
          if (a) { a.click(); return true; }
          return false;
        });
        if (!nextBtn) break;
        await sleep(2500);
        const retry = await page.evaluate(() => {
          const isVisible = (el) => {
            const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const rows = Array.from(document.querySelectorAll('tbody.table_body tr.table_tr'));
          for (const row of rows) {
            if (!(row.innerText || '').includes('审核通过')) continue;
            const link = row.querySelector('a[href="javascript:;"]');
            if (link && isVisible(link)) { link.click(); return true; }
          }
          return false;
        });
        if (retry) { found = true; console.log('  ✅ 在下一页找到并点开详情'); }
      }
      if (!found) {
        await page.screenshot({ path: path.join(__dirname, 'inspect_detail_home.png') });
        console.error('❌ 翻 3 页都没找到「审核通过」单曲，无法探测详情页。');
        await browser.disconnect().catch(() => {});
        process.exit(1);
      }
    } else {
      console.log('  ✅ 已点击详情:', detailClicked.rowTextHead);
    }

    // 3. 等详情页出现。判断是新 tab 还是同页弹窗/跳转
    console.log('⏳ 等待详情页加载...');
    let detailPage = page;
    let openMode = 'unknown';
    await sleep(4000);

    const pagesAfter = await browser.pages();
    if (pagesAfter.length > pagesBefore) {
      // 新 tab 打开
      detailPage = pagesAfter[pagesAfter.length - 1];
      await detailPage.waitForSelector('body', { timeout: 15000 }).catch(() => {});
      openMode = 'new_tab';
      console.log('  ✅ 详情页以【新标签页】打开');
    } else {
      // 等几秒看 URL 是否变化 / 是否出现弹窗
      const urlAfter = detailPage.url();
      if (urlAfter !== urlBefore) {
        openMode = 'same_page_navigate';
        console.log('  ✅ 详情页【同页跳转】: ' + urlAfter);
      } else {
        openMode = 'same_page_dialog';
        console.log('  ✅ 详情页【同页弹窗】（URL 未变）');
      }
    }
    await sleep(3000); // 再等渲染

    console.log('🔍 开始只读 dump 详情页 DOM 结构... 当前URL:', detailPage.url());

    // 4. 只读 dump 详情页结构
    const report = await detailPage.evaluate(() => {
      const result = {};
      result.url = location.href;
      result.title = document.title;
      result.bodyTextHead = (document.body.innerText || '').slice(0, 2000);

      // 4.1 weui-desktop class 频次
      const classCounter = {};
      document.querySelectorAll('*').forEach(el => {
        if (!el.className || typeof el.className !== 'string') return;
        el.className.split(/\s+/).forEach(c => {
          if (c && c.startsWith('weui-desktop')) classCounter[c] = (classCounter[c] || 0) + 1;
        });
      });
      result.weuiClasses = Object.entries(classCounter).sort((a, b) => b[1] - a[1]).slice(0, 50);

      // 4.2 所有可见 primary 按钮（找「上架」「预约」）
      const primaryBtns = [];
      document.querySelectorAll('button, a, .weui-desktop-btn_primary').forEach(btn => {
        const t = (btn.innerText || btn.textContent || '').trim();
        if (!t || t.length > 30) return;
        const s = window.getComputedStyle(btn), r = btn.getBoundingClientRect();
        const visible = s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        if (!visible) return;
        const isPrimary = (btn.className || '').includes('primary');
        if (!isPrimary && !/上架|预约|确定|确认|提交/.test(t)) return;
        primaryBtns.push({
          text: t.slice(0, 30),
          tag: btn.tagName,
          cls: btn.className,
          dataV: Array.from(btn.attributes || []).filter(a => a.name.startsWith('data-v-')).map(a => a.name).join(' '),
          type: btn.getAttribute('type') || '',
          disabled: !!btn.disabled || btn.getAttribute('aria-disabled') === 'true',
          visible,
          x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
          // 上下文（找最近的卡片/区块容器）
          contextText: (btn.closest('[class*="card"],[class*="box"],[class*="panel"],[class*="dialog"],[class*="modal"],section,fieldset,form') || {}).innerText
            ? (btn.closest('[class*="card"],[class*="box"],[class*="panel"],[class*="dialog"],[class*="modal"],section,fieldset,form').innerText || '').slice(0, 200).replace(/\s+/g, ' ').trim() : '',
        });
      });
      result.primaryButtons = primaryBtns;

      // 4.3 所有 svg（找日历图标）
      const svgs = [];
      document.querySelectorAll('svg').forEach(svg => {
        const s = window.getComputedStyle(svg), r = svg.getBoundingClientRect();
        const visible = s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        if (!visible) return;
        const firstPath = svg.querySelector('path');
        svgs.push({
          viewBox: svg.getAttribute('viewBox') || '',
          cls: svg.className || '',
          pathCount: svg.querySelectorAll('path').length,
          firstPathD: firstPath ? (firstPath.getAttribute('d') || '').slice(0, 60) : '',
          w: Math.round(r.width), h: Math.round(r.height),
          clickableAncestor: (() => {
            let p = svg.parentElement, depth = 0;
            while (p && depth < 5) {
              if (p.tagName === 'BUTTON' || p.tagName === 'A' || p.getAttribute('onclick') || (p.className || '').toString().includes('input')) {
                return { tag: p.tagName, cls: p.className, role: p.getAttribute('role') || '' };
              }
              p = p.parentElement; depth++;
            }
            return null;
          })(),
          // input 父级（很可能是日期选择器的输入框）
          inputAncestor: (() => {
            let p = svg.parentElement, depth = 0;
            while (p && depth < 5) {
              if (p.tagName === 'INPUT' || p.querySelector(':scope > input')) return true;
              p = p.parentElement; depth++;
            }
            return false;
          })(),
        });
      });
      result.svgs = svgs;

      // 4.4 日期/日历相关元素
      const dateNodes = [];
      document.querySelectorAll('[class*="date"],[class*="calendar"],[class*="picker"],[class*="time"],input[type="date"],input[placeholder*="日期"],input[placeholder*="时间"],input[placeholder*="上架"]').forEach(el => {
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        const visible = s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        dateNodes.push({
          tag: el.tagName, cls: el.className,
          type: el.getAttribute('type') || '',
          placeholder: el.getAttribute('placeholder') || '',
          value: el.value || '',
          visible,
        });
      });
      result.dateNodes = dateNodes.slice(0, 30);

      // 4.5 弹窗/对话框/遮罩结构（判断是否模态）
      const dialogs = [];
      document.querySelectorAll('.weui-desktop-dialog__wrp,[class*="dialog"],[class*="modal"],[class*="mask"],[class*="overlay"]').forEach(el => {
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        const visible = s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || '1') > 0.3;
        dialogs.push({
          tag: el.tagName, cls: el.className, visible,
          display: s.display, zIndex: s.zIndex,
          headText: (el.innerText || '').slice(0, 150).replace(/\s+/g, ' ').trim(),
        });
      });
      result.dialogs = dialogs.slice(0, 15);

      // 4.6 关键文案定位（上架/预约/今日/弹数/状态）
      const keywords = ['上架', '预约', '今日', '今天', '定时', '立即', '已预约', '预约成功', '上架成功', '提交', '取消', '关闭'];
      const keywordNodes = {};
      const walk = (node) => {
        if (node.nodeType !== 1) return;
        const ownText = Array.from(node.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
        keywords.forEach(kw => {
          if (ownText === kw || (ownText.length < 25 && ownText.includes(kw))) {
            keywordNodes[kw] = keywordNodes[kw] || [];
            if (keywordNodes[kw].length < 4) {
              keywordNodes[kw].push({
                tag: node.tagName, cls: node.className,
                text: ownText.slice(0, 40),
                parentCls: node.parentElement ? node.parentElement.className : '',
              });
            }
          }
        });
        Array.from(node.children).forEach(walk);
      };
      walk(document.body);
      result.keywordNodes = keywordNodes;

      // 4.7 返回/关闭按钮候选（详情页如何回去）
      const closeCandidates = [];
      document.querySelectorAll('a,button,span,[class*="close"],[class*="back"],[class*="return"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t.length > 10) return;
        if (!/返回|关闭|×|✕|back|close|取消|查看更多|我的表情/.test(t)) return;
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        const visible = s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        closeCandidates.push({ text: t, tag: el.tagName, cls: el.className, visible, href: el.getAttribute && el.getAttribute('href') || '' });
      });
      result.closeCandidates = closeCandidates.slice(0, 20);

      return result;
    });

    report.openMode = openMode;
    report.pagesBefore = pagesBefore;
    report.pagesAfter = (await browser.pages()).length;

    // 4.8 详情页关键区块 HTML（含「上架」按钮的容器）
    try {
      const html = await detailPage.evaluate(() => {
        const btn = Array.from(document.querySelectorAll('button.weui-desktop-btn_primary')).find(b => /上架/.test(b.innerText || ''));
        const ctx = btn && (btn.closest('[class*="card"],[class*="box"],[class*="panel"],section,fieldset,form,div') );
        return ctx ? ctx.outerHTML.slice(0, 3000) : '';
      });
      report.shelfButtonContainerHtml = html;
    } catch (e) { report.shelfButtonContainerHtml = '(获取失败: ' + e.message + ')'; }

    fs.writeFileSync(OUT_FILE, JSON.stringify(report, null, 2), 'utf-8');
    console.log('\n✅ 探测完成，结果已写入:', OUT_FILE);
    console.log('\n=== 摘要 ===');
    console.log('打开方式:', openMode);
    console.log('primary/操作按钮数:', report.primaryButtons.length);
    console.log('svg(含日历)数:', report.svgs.length);
    console.log('日期相关元素数:', report.dateNodes.length);
    console.log('弹窗/遮罩数:', report.dialogs.length);
    console.log('关键文案 keys:', Object.keys(report.keywordNodes).join(', '));

    await browser.disconnect().catch(() => {});
    console.log('\n（已 disconnect，未关闭浏览器，登录态保留）');
  } catch (e) {
    console.error('❌ 探测出错:', e);
    try { await page.screenshot({ path: path.join(__dirname, 'inspect_detail_error.png') }); } catch (_) {}
    await browser.disconnect().catch(() => {});
    process.exit(1);
  }
})();
