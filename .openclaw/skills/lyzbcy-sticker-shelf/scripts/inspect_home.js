/**
 * inspect_home.js — 首页「我的作品管理」列表只读探测脚本
 *
 * 用途：自动登录后，只读 dump 首页真实 DOM 结构，
 *       为 shelf.js 主脚本固化准确的 CSS 选择器。
 *
 * 🔴 安全保证：
 *   - 只用 page.evaluate 读取，不点击、不提交、不改任何状态
 *   - 不上传任何文件、不触发任何上架动作
 *   - 登录是唯一会改变状态的动作（必要前置），之后纯只读
 *
 * 用法：
 *   node inspect_home.js            # 自动登录 + 导航首页 + dump DOM
 */

const path = require('path');
const fs = require('fs');
const { HOME_URL, sleep, loadCredentials, launchBrowser, ensureLogin } = require('./wechat-launch');

const OUT_FILE = path.join(__dirname, 'inspect_home_result.json');

(async () => {
  console.log('=== 首页只读探测脚本启动 ===');

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

    // 登录成功后若被重定向走，重新确保在首页列表
    if (!page.url().includes('home/index') && !page.url().includes('home')) {
      console.log('📍 重新导航回首页列表...');
      await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
      await sleep(3000);
    } else {
      await sleep(3000);
    }

    console.log('🔍 开始只读 dump DOM 结构... 当前URL:', page.url());

    const report = await page.evaluate(() => {
      const result = {
        url: location.href,
        title: document.title,
        bodyTextHead: (document.body.innerText || '').slice(0, 1000),
      };

      // 1. weui-desktop class 频次
      const classCounter = {};
      document.querySelectorAll('*').forEach(el => {
        if (!el.className || typeof el.className !== 'string') return;
        el.className.split(/\s+/).forEach(c => {
          if (c && c.startsWith('weui-desktop')) classCounter[c] = (classCounter[c] || 0) + 1;
        });
      });
      result.weuiClasses = Object.entries(classCounter).sort((a, b) => b[1] - a[1]).slice(0, 40);

      // 2. 列表容器候选
      const candidates = [];
      document.querySelectorAll('div, table, ul, tbody').forEach(container => {
        const children = Array.from(container.children);
        if (children.length < 2) return;
        const childClasses = children.map(c => (c.className || '').toString().split(/\s+/)[0]);
        const sameClassRatio = childClasses.filter(c => c && c === childClasses[0]).length / children.length;
        if (sameClassRatio < 0.6) return;
        const textLen = children.reduce((s, c) => s + (c.innerText || '').length, 0);
        if (textLen < 20) return;
        candidates.push({
          tag: container.tagName, cls: container.className,
          childCount: children.length, childTag: children[0].tagName, childClass: children[0].className,
          sampleChildText: (children[0].innerText || '').slice(0, 200),
          sameClassRatio: Math.round(sameClassRatio * 100) / 100,
        });
      });
      result.listCandidates = candidates.sort((a, b) => b.childCount - a.childCount).slice(0, 8);

      // 3. 状态标签文字
      const statusKeywords = ['审核通过', '审核中', '已上架', '已下架', '上架', '预约', '详情', '编辑', '删除'];
      const statusNodes = [];
      const walk = (node) => {
        if (node.nodeType !== 1) return;
        const ownText = Array.from(node.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
        statusKeywords.forEach(kw => {
          if (ownText === kw) {
            statusNodes.push({
              text: kw, tag: node.tagName, cls: node.className,
              parentCls: node.parentElement ? node.parentElement.className : '',
              clickableAncestor: (() => {
                let p = node, depth = 0;
                while (p && depth < 5) {
                  if (p.tagName === 'A' || p.tagName === 'BUTTON' || p.getAttribute('onclick')) {
                    return { tag: p.tagName, cls: p.className, href: p.getAttribute('href') || '' };
                  }
                  p = p.parentElement; depth++;
                }
                return null;
              })(),
            });
          }
        });
        Array.from(node.children).forEach(walk);
      };
      walk(document.body);
      const grouped = {};
      statusNodes.forEach(n => { grouped[n.text] = grouped[n.text] || []; if (grouped[n.text].length < 5) grouped[n.text].push(n); });
      result.statusNodes = grouped;
      result.statusCounts = Object.fromEntries(
        Object.entries(grouped).map(([k]) => [k, statusNodes.filter(n => n.text === k).length])
      );

      // 4. 分页控件
      const pageMarkers = [];
      document.querySelectorAll('*').forEach(el => {
        const t = (el.innerText || '').trim();
        const visible = (() => { const s = getComputedStyle(el), r = el.getBoundingClientRect(); return s.display !== 'none' && r.width > 0 && r.height > 0; })();
        if (/^(上一页|下一页|首页|末页)$/.test(t) && el.children.length === 0) {
          pageMarkers.push({ text: t, tag: el.tagName, cls: el.className, visible });
        }
        if (/^\d{1,3}$/.test(t) && el.children.length === 0 && visible) {
          const parent = el.parentElement;
          if (parent) {
            const sibs = Array.from(parent.children).filter(c => /^\d{1,3}$/.test((c.innerText || '').trim()) && c.children.length === 0);
            if (sibs.length >= 2) pageMarkers.push({ text: t, tag: el.tagName, cls: el.className, parentCls: parent.className, siblingCount: sibs.length });
          }
        }
      });
      result.pagination = pageMarkers.slice(0, 25);

      // 5. 筛选 tab
      const filterTabs = [];
      const filterKws = ['全部', '审核中', '审核通过', '已上架', '已下架', '待上架'];
      document.querySelectorAll('a, span, div, li, button').forEach(el => {
        const t = (el.innerText || '').trim();
        if (filterKws.includes(t) && el.children.length === 0) {
          const visible = (() => { const s = getComputedStyle(el), r = el.getBoundingClientRect(); return s.display !== 'none' && r.width > 0 && r.height > 0; })();
          filterTabs.push({ text: t, tag: el.tagName, cls: el.className, visible });
        }
      });
      result.filterTabs = filterTabs.slice(0, 25);

      // 6. svg
      const svgs = [];
      document.querySelectorAll('svg').forEach(svg => {
        const visible = (() => { const s = getComputedStyle(svg), r = svg.getBoundingClientRect(); return s.display !== 'none' && r.width > 0 && r.height > 0; })();
        svgs.push({
          viewBox: svg.getAttribute('viewBox') || '', cls: svg.className, visible, pathCount: svg.querySelectorAll('path').length,
          clickableAncestor: (() => {
            let p = svg.parentElement, depth = 0;
            while (p && depth < 4) {
              if (p.tagName === 'BUTTON' || p.tagName === 'A' || p.getAttribute('onclick')) return { tag: p.tagName, cls: p.className };
              p = p.parentElement; depth++;
            }
            return null;
          })(),
        });
      });
      result.svgs = svgs.slice(0, 20);

      // 7. primary 按钮
      const primaryBtns = [];
      document.querySelectorAll('button.weui-desktop-btn_primary, .weui-desktop-btn_primary').forEach(btn => {
        const t = (btn.innerText || '').trim();
        if (!t) return;
        const visible = (() => { const s = getComputedStyle(btn), r = btn.getBoundingClientRect(); return s.display !== 'none' && r.width > 0 && r.height > 0; })();
        primaryBtns.push({
          text: t.slice(0, 30), tag: btn.tagName, cls: btn.className, visible,
          contextText: btn.closest('tr, li, [class*="item"], [class*="card"], [class*="row"]')
            ? btn.closest('tr, li, [class*="item"], [class*="card"], [class*="row"]').innerText.slice(0, 150) : '',
        });
      });
      result.primaryButtons = primaryBtns.slice(0, 30);

      return result;
    });

    // 8. 样例行 HTML
    try {
      const sampleHtml = await page.evaluate(() => {
        const rows = document.querySelectorAll('tr, li, [class*="item__"], [class*="list-item"], [class*="row"]');
        for (const row of rows) {
          const t = (row.innerText || '').trim();
          if (t.includes('审核通过') || t.includes('审核中') || t.includes('上架') || t.includes('详情')) {
            return row.outerHTML.slice(0, 2500);
          }
        }
        return '';
      });
      report.sampleRowHtml = sampleHtml;
    } catch (e) { report.sampleRowHtml = '(获取失败: ' + e.message + ')'; }

    fs.writeFileSync(OUT_FILE, JSON.stringify(report, null, 2), 'utf-8');
    console.log('\n✅ 探测完成，结果已写入:', OUT_FILE);
    console.log('\n=== 摘要 ===');
    console.log('状态统计:', JSON.stringify(report.statusCounts));
    console.log('列表候选数:', report.listCandidates.length);
    console.log('分页元素数:', report.pagination.length);
    console.log('筛选 tab 数:', report.filterTabs.length);
    console.log('primary 按钮数:', report.primaryButtons.length);
    console.log('svg 数:', report.svgs.length);

    await browser.disconnect().catch(() => {});
    console.log('\n（已 disconnect，未关闭浏览器，登录态保留）');
  } catch (e) {
    console.error('❌ 探测出错:', e);
    await browser.disconnect().catch(() => {});
    process.exit(1);
  }
})();
