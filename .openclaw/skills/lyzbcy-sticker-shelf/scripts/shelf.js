/**
 * shelf.js — 自动上架「审核通过」的微信表情专辑（主脚本）
 *
 * 对应需求 .openclaw/自动将检测通过的发布.md 的 7 步流程：
 *   1. 打开首页，定位「审核通过」单曲行
 *   2. 点对应「详情」(a[href="javascript:;"])
 *   3. 等详情页加载（同页跳转到 stickerPage/setting?stikerid=...）
 *   4. 点「上架」按钮 (div[data-v-e67065cd] button.weui-desktop-btn_primary)
 *   5. 在「预约上架」弹窗点日历「今日」(a.weui-desktop-picker__current)
 *   6. 点「预约」按钮 (div.weui-desktop-dialog__ft button.weui-desktop-btn_primary)
 *   7. 确认预约成功 → 返回列表继续下一个
 *
 * 翻页策略（需求）：从 min(5, 总页数) 页往前逐页处理，
 *   保证先通过审核的（低弹数）先上架，上架顺序尽量按弹数从低到高。
 *
 * 自我审查（需求）：每页处理完后刷新该页，检查是否还有「审核通过」残留。
 *
 * 复用 wechat-launch.js：共享 publisher 的登录态 + .env 凭据。
 *
 * 用法：
 *   node shelf.js                    # 默认最多翻 5 页
 *   node shelf.js --max-pages 3      # 自定义最大页数
 *   node shelf.js --dry-run          # 只探测不上架（只点详情，不点上架/预约）
 */

const path = require('path');
const fs = require('fs');
const { HOME_URL, sleep, loadCredentials, launchBrowser, ensureLogin } = require('./wechat-launch');

const OUT_FILE = path.join(__dirname, '_shelf_result.json');

// ---------- 参数 ----------
const argv = process.argv.slice(2);
const opts = { maxPages: 5, dryRun: false, limit: 0 };
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--max-pages') opts.maxPages = parseInt(argv[++i]) || 5;
  else if (argv[i] === '--dry-run') opts.dryRun = true;
  else if (argv[i] === '--limit') opts.limit = parseInt(argv[++i]) || 0;
}

// ---------- 通用辅助 ----------
const is = (el, s) => { const c = (el && el.className) || ''; return typeof c === 'string' ? c.includes(s) : false; };

/** 在页面里找第一个可见「上架」主按钮（严格检查可见性 + 在详情页 data-v-e67065cd 作用域内） */
async function findShelfButton(page) {
  return page.evaluate(() => {
    // 优先在详情页上架区块 [data-v-e67065cd] 内找
    const scope = document.querySelector('[data-v-e67065cd]');
    const pool = scope ? scope.querySelectorAll('button.weui-desktop-btn_primary')
                       : document.querySelectorAll('button.weui-desktop-btn_primary');
    for (const b of Array.from(pool)) {
      if (!/上架/.test(b.innerText || '') || b.disabled) continue;
      const s = window.getComputedStyle(b), r = b.getBoundingClientRect();
      if (s.display === 'none' || s.visibility === 'hidden' || r.width <= 0 || r.height <= 0) continue;
      return { found: true, x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height };
    }
    return null;
  });
}

/** 找「预约上架」弹窗里的「预约」按钮 */
async function findReserveButton(page) {
  return page.evaluate(() => {
    // 弹窗：div.weui-desktop-dialog__ft 内的 primary 按钮，文本「预约」
    const fts = Array.from(document.querySelectorAll('.weui-desktop-dialog__ft, .dialog_shelf .weui-desktop-dialog__ft'));
    for (const ft of fts) {
      const btn = Array.from(ft.querySelectorAll('button.weui-desktop-btn_primary'))
        .find(x => /预约/.test(x.innerText || '') && !x.disabled);
      if (btn) {
        const r = btn.getBoundingClientRect();
        const s = window.getComputedStyle(btn);
        if (s.display === 'none' || s.visibility === 'hidden') continue;
        return { found: true, x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
    }
    // 兜底：全局找可见「预约」primary 按钮
    const any = Array.from(document.querySelectorAll('button.weui-desktop-btn_primary'))
      .find(x => (x.innerText || '').trim() === '预约' && !x.disabled);
    if (any) {
      const r = any.getBoundingClientRect();
      return { found: true, x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }
    return null;
  });
}

/** 点击日历「今日」单元格（保险动作，点不到不报错——默认就已选中今日） */
async function clickToday(page) {
  const got = await page.evaluate(() => {
    // 今日：a.weui-desktop-picker__current
    let cell = document.querySelector('a.weui-desktop-picker__current');
    // 兜底：可见 picker 面板里带 today/当前 语义的单元格
    if (!cell) {
      cell = Array.from(document.querySelectorAll('.weui-desktop-picker__panel_day a, .weui-desktop-picker__table a'))
        .find(a => /current|today|今日/.test(a.className || '') || /current|today/.test(a.getAttribute('data-class') || ''));
    }
    if (!cell) return { ok: false, reason: 'not_found' };
    const r = cell.getBoundingClientRect();
    const s = window.getComputedStyle(cell);
    if (s.display === 'none') return { ok: false, reason: 'hidden' };
    cell.click();
    return { ok: true, x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  if (got.ok) {
    await page.mouse.click(got.x, got.y).catch(() => {});
    await sleep(400);
  }
  return got;
}

/** 等待「预约上架」弹窗真正弹出。
 *  注意：.dialog_shelf 容器恒显 display:block，不能用它判断；
 *  正确信号是 .weui-desktop-dialog__wrp + .weui-desktop-mask 出现（display!=none），
 *  且 body 出现「预约上架」文案。 */
async function waitForShelfDialog(page, timeout = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    let visible = false;
    try {
      visible = await page.evaluate(() => {
        const wrp = document.querySelector('.dialog_shelf .weui-desktop-dialog__wrp, .weui-desktop-dialog__wrp');
        const mask = document.querySelector('.weui-desktop-mask');
        const wrpShow = wrp && getComputedStyle(wrp).display !== 'none';
        const maskShow = mask && getComputedStyle(mask).display !== 'none';
        const hasTitle = (document.body.innerText || '').includes('预约上架');
        return (wrpShow && maskShow) || hasTitle;
      });
    } catch (e) { /* 导航中，继续等 */ }
    if (visible) return true;
    await sleep(500);
  }
  return false;
}

/** 确认预约成功：弹窗消失 或 出现成功文案 或 状态变化 */
async function confirmReserveSuccess(page, timeout = 20000) {
  const start = Date.now();
  let sawSuccess = false;
  while (Date.now() - start < timeout) {
    const state = await page.evaluate(() => {
      const body = document.body ? document.body.innerText : '';
      // 弹窗是否还在
      const dlg = document.querySelector('.dialog_shelf');
      const dlgVisible = dlg && (() => {
        const s = window.getComputedStyle(dlg), r = dlg.getBoundingClientRect();
        return s.display !== 'none' && r.width > 0;
      })();
      // 成功/已预约标志
      const success = /已预约|预约成功|上架成功|操作成功|已提交/.test(body);
      return { dlgVisible, success };
    });
    if (state.success) { sawSuccess = true; break; }
    if (state.dlgVisible === false && (Date.now() - start) > 3000) {
      // 弹窗消失了（且已过 3s 缓冲）也算成功
      sawSuccess = true; break;
    }
    await sleep(700);
  }
  return sawSuccess;
}

/** 返回首页列表 */
async function backToHome(page) {
  // 优先用浏览器返回（同页跳转，back 即回到列表）
  try {
    await page.goBack({ waitUntil: 'domcontentloaded', timeout: 20000 });
  } catch (e) {
    // 兜底：直接 goto 首页
    await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
  }
  await sleep(2000);
  // 确保在首页
  if (!page.url().includes('home/index') && !page.url().includes('home')) {
    await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    await sleep(2000);
  }
}

/** 获取当前页「审核通过」单曲行信息（不含形象行） */
async function getPassedAlbums(page) {
  return page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('tbody.table_body tr.table_tr'));
    const out = [];
    rows.forEach((row, idx) => {
      const txt = row.innerText || '';
      if (!txt.includes('审核通过')) return;
      // 单曲详情链接（href="javascript:;"），排除形象详情（href*="ip/detail"）
      const link = row.querySelector('a[href="javascript:;"]');
      if (!link) return;
      // 取行内首个表情名（去掉状态/日期等噪声）
      const name = txt.split(/\n|审核通过/)[0].trim().split(/\s+/)[0] || ('行' + idx);
      out.push({ rowIdx: idx, name, hasLink: !!link });
    });
    return out;
  });
}

/** 读取首页总页数 */
async function getTotalPages(page) {
  return page.evaluate(() => {
    // label.weui-desktop-pagination__num 有两个：当前页 / 总页数，取最后一个
    const nums = Array.from(document.querySelectorAll('.weui-desktop-pagination__num, label.weui-desktop-pagination__num'));
    const texts = nums.map(n => (n.innerText || '').trim()).filter(t => /^\d+$/.test(t));
    if (texts.length === 0) return 1;
    return parseInt(texts[texts.length - 1]);
  }).catch(() => 1);
}

/** 跳到指定页码（用「跳转」输入框；失败则翻页） */
async function gotoPage(page, target) {
  // 1. 先试「跳转」输入框
  const jumped = await page.evaluate((tgt) => {
    const input = document.querySelector('.weui-desktop-pagination__input, input[type="text"]');
    if (!input) return false;
    const form = input.closest('form') || input.parentElement;
    // 找跳转按钮
    const goBtn = Array.from(document.querySelectorAll('button, a')).find(el =>
      /跳转|确定|go/i.test(el.innerText || '') && el.getBoundingClientRect().width > 0
    );
    const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSet.call(input, String(tgt));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    if (goBtn) { goBtn.click(); return true; }
    if (form && form.tagName === 'FORM') { form.submit(); return true; }
    return false;
  }, target);
  if (jumped) { await sleep(2500); return; }

  // 2. 兜底：用「上一页」逐页往前
  for (let attempt = 0; attempt < 20; attempt++) {
    const cur = await getCurrentPage(page);
    if (cur <= target) break;
    const ok = await page.evaluate(() => {
      const a = Array.from(document.querySelectorAll('a')).find(el =>
        (el.innerText || '').trim() === '上一页' && el.getBoundingClientRect().width > 0 &&
        !el.className.includes('disabled') && !el.parentElement.className.includes('disabled'));
      if (a) { a.click(); return true; }
      return false;
    });
    if (!ok) break;
    await sleep(2000);
  }
}

/** 读取当前页码 */
async function getCurrentPage(page) {
  return page.evaluate(() => {
    const nums = Array.from(document.querySelectorAll('.weui-desktop-pagination__num, label.weui-desktop-pagination__num'));
    const texts = nums.map(n => (n.innerText || '').trim()).filter(t => /^\d+$/.test(t));
    return texts.length ? parseInt(texts[0]) : 1;
  }).catch(() => 1);
}

/** 处理单个「审核通过」专辑：点详情 → 上架 → 选今日 → 预约 */
async function shelveOne(page, album, dryRun) {
  const log = (m) => console.log('      ' + m);
  const result = { name: album.name, status: 'UNKNOWN', reason: '' };

  // 1. 点该行的「详情」（重新定位，避免行索引漂移）
  const clicked = await page.evaluate((name) => {
    const isVisible = (el) => {
      const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    };
    const rows = Array.from(document.querySelectorAll('tbody.table_body tr.table_tr'));
    for (const row of rows) {
      const txt = row.innerText || '';
      if (!txt.includes('审核通过')) continue;
      if (name && !txt.includes(name)) continue;
      const link = row.querySelector('a[href="javascript:;"]');
      if (link && isVisible(link)) { link.click(); return true; }
    }
    return false;
  }, album.name);

  if (!clicked) {
    result.status = 'FAIL'; result.reason = '未找到详情链接（行可能已变化）';
    log('❌ ' + result.reason); return result;
  }
  log('✅ 已点详情: ' + album.name);

  // 2. 等详情页真正加载完成：URL 必须跳到 stickerPage/setting，
  //    且出现 data-v-e67065cd 上架区块（首页残留的「提交作品」按钮会误判，故用此专属标记）
  //    注意：详情是 SPA 同页跳转，点击后导航期间 evaluate 会抛 "context destroyed"，
  //    所以先 sleep 让跳转发生，轮询里再容错重试。
  await sleep(2500); // 让点击触发的导航完成
  let detailReady = false;
  for (let w = 0; w < 30; w++) { // 最多 ~30s
    let state = null;
    try {
      state = await page.evaluate(() => ({
        onDetail: /stickerPage\/setting/.test(location.href),
        hasShelfScope: !!document.querySelector('[data-v-e67065cd]'),
      }));
    } catch (e) { // 导航中 context 销毁，等一下重试
      await sleep(1000);
      continue;
    }
    if (state && state.onDetail && state.hasShelfScope) { detailReady = true; break; }
    await sleep(1000);
  }
  if (!detailReady) {
    // 仍在首页或无上架区块 → 可能点详情未生效，回首页报错
    result.status = 'FAIL'; result.reason = '详情页未加载（未跳转到 stickerPage/setting 或无上架区块）';
    log('❌ ' + result.reason);
    await backToHome(page);
    return result;
  }
  log('✅ 详情页已就绪');
  await sleep(1500); // 让按钮完全可交互

  // 3. 找「上架」按钮（轮询，最多 ~10s，应对懒渲染）
  let shelfBtn = null;
  for (let w = 0; w < 10 && !shelfBtn; w++) {
    try { shelfBtn = await findShelfButton(page); } catch (e) { /* 导航中，重试 */ }
    if (!shelfBtn) await sleep(1000);
  }
  if (!shelfBtn) {
    // 可能该专辑状态已变（如已上架/已预约），记录并返回
    result.status = 'SKIP'; result.reason = '详情页无可见「上架」按钮（可能已上架/已预约）';
    log('⚠️ ' + result.reason);
    await backToHome(page);
    return result;
  }
  log('📍 找到「上架」按钮');

  if (dryRun) {
    result.status = 'DRY_RUN'; result.reason = 'dry-run 模式，未点上架';
    log('🟡 [dry-run] 跳过上架');
    await backToHome(page);
    return result;
  }

  // 4. 点「上架」→ 等弹窗（先 move 再 click，模拟真人，避免 Vue 事件未触发）
  await page.mouse.move(shelfBtn.x, shelfBtn.y);
  await sleep(200);
  await page.mouse.click(shelfBtn.x, shelfBtn.y);
  log('✅ 已点「上架」');
  const dlgOk = await waitForShelfDialog(page, 15000);
  if (!dlgOk) {
    result.status = 'FAIL'; result.reason = '点击上架后「预约上架」弹窗未出现';
    log('❌ ' + result.reason);
    await page.screenshot({ path: path.join(__dirname, 'screenshot_no_dialog_' + Date.now() + '.png') }).catch(() => {});
    await backToHome(page);
    return result;
  }
  log('✅ 「预约上架」弹窗已出现');
  await sleep(1200);

  // 5. 选「今日」（保险；默认已选中今日，点不到不报错）
  const today = await clickToday(page);
  log(today.ok ? '✅ 已选「今日」' : 'ℹ️ 未单独点今日（默认已选中，继续）');
  await sleep(800);

  // 6. 找「预约」按钮并点击
  const reserveBtn = await findReserveButton(page);
  if (!reserveBtn) {
    result.status = 'FAIL'; result.reason = '弹窗内未找到「预约」按钮';
    log('❌ ' + result.reason);
    await backToHome(page);
    return result;
  }
  await page.mouse.click(reserveBtn.x, reserveBtn.y);
  log('✅ 已点「预约」');

  // 7. 确认成功
  const success = await confirmReserveSuccess(page, 20000);
  if (success) {
    result.status = 'OK'; result.reason = '';
    log('🎉 预约成功');
  } else {
    result.status = 'UNKNOWN'; result.reason = '点预约后未确认到成功标志（请人工核对）';
    log('⚠️ ' + result.reason);
    await page.screenshot({ path: path.join(__dirname, 'screenshot_uncertain_' + Date.now() + '.png') }).catch(() => {});
  }

  // 返回列表
  await backToHome(page);
  return result;
}

// ---------- 主流程 ----------
(async () => {
  console.log('=== 自动上架脚本启动 ===');
  console.log('参数: maxPages=' + opts.maxPages + (opts.dryRun ? ' | DRY-RUN' : '') + (opts.limit > 0 ? ' | LIMIT=' + opts.limit : ''));
  if (!opts.dryRun) {
    console.log('⚠️ 这是真实上架操作，将预约今日上架「审核通过」的专辑。');
  }

  const creds = loadCredentials();
  const browser = await launchBrowser();
  const page = await browser.newPage();
  page.setDefaultTimeout(300000);

  const allResults = [];

  try {
    // A. 登录 + 进首页
    console.log('📍 打开首页...');
    for (let attempt = 0; attempt < 3; attempt++) {
      try { await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }); break; }
      catch (e) { if (attempt < 2) await sleep(3000); }
    }
    const ok = await ensureLogin(page, creds);
    if (!ok) { console.error('❌ 登录失败，终止。'); await browser.disconnect().catch(() => {}); process.exit(1); }
    if (!page.url().includes('home/index') && !page.url().includes('home')) {
      await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    }
    await sleep(3000);

    // B. 读总页数
    const total = await getTotalPages(page);
    const startPage = Math.min(opts.maxPages, total);
    console.log('📖 总页数: ' + total + ' | 从第 ' + startPage + ' 页开始往前处理');

    // C. 从 startPage 往前到第 1 页
    for (let pg = startPage; pg >= 1; pg--) {
      console.log('\n' + '='.repeat(50));
      console.log('📄 处理第 ' + pg + ' 页');
      console.log('='.repeat(50));

      if (pg !== await getCurrentPage(page)) {
        await gotoPage(page, pg);
        await sleep(2000);
        const realCur = await getCurrentPage(page);
        if (realCur !== pg) {
          console.log('⚠️ 跳转到第 ' + pg + ' 页失败，实际在第 ' + realCur + ' 页，跳过该页');
          continue;
        }
      }

      // 处理本页所有「审核通过」。用 processed 集合按 name 去重，避免
      // dry-run/SKIP（不改变平台状态）导致列表不变而死循环重复处理同一项。
      let pageNumResults = [];
      const processed = new Set();
      let safety = 0;
      while (safety++ < 60) {
        // limit 计所有尝试过的项（含 FAIL/SKIP），避免小范围测试时一个失败连点多个
        if (opts.limit > 0 && pageNumResults.length >= opts.limit) {
          console.log('  ⏹️ 已达到 --limit ' + opts.limit + '，停止本页处理');
          break;
        }
        const albums = await getPassedAlbums(page);
        const todo = albums.filter(a => !processed.has(a.name));
        if (todo.length === 0) break; // 本页能处理的都处理过了
        console.log('  🔍 本页「审核通过」共 ' + albums.length + ' 个，剩余待处理 ' + todo.length + ' 个 → ' + todo.map(a => a.name).join(', '));
        const one = todo[0];
        processed.add(one.name);
        console.log('  🎯 处理: ' + one.name);
        const r = await shelveOne(page, one, opts.dryRun);
        pageNumResults.push(r);
        allResults.push({ page: pg, ...r });
        // 每次上架后回首页，确保停在该页
        await sleep(1500);
        const cur = await getCurrentPage(page);
        if (cur !== pg) {
          await gotoPage(page, pg);
          await sleep(1500);
        }
      }

      // limit 模式：达到上限就跳过自我审查，直接结束
      if (opts.limit > 0 && pageNumResults.length >= opts.limit) {
        console.log('  ⏹️ 达到 --limit ' + opts.limit + '，跳过自我审查');
        break; // 退出外层 for pg 循环
      }

      // 自我审查：刷新该页再查一次。只补处理「主轮次未碰过的新残留」，
      // 对已处理过的（processed 里的）不重复点上架——避免对失败/已预约项反复点击。
      if (!opts.dryRun && pageNumResults.length > 0) {
        console.log('\n  🔎 [自我审查] 刷新第 ' + pg + ' 页复查残留...');
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
        await sleep(2500);
        await gotoPage(page, pg);
        await sleep(1500);
        const remain = await getPassedAlbums(page);
        const newOnes = remain.filter(a => !processed.has(a.name));
        const staleOnes = remain.filter(a => processed.has(a.name));
        if (staleOnes.length > 0) {
          console.log('  ℹ️ 已处理过仍显示「审核通过」（可能状态延迟或预约待生效），不重复点击: ' + staleOnes.map(a => a.name).join(', '));
        }
        if (newOnes.length > 0) {
          console.log('  ⚠️ 复查发现新残留 ' + newOnes.length + ' 个，补处理: ' + newOnes.map(a => a.name).join(', '));
          for (const one of newOnes) {
            processed.add(one.name);
            const r = await shelveOne(page, one, opts.dryRun);
            allResults.push({ page: pg, review: true, ...r });
            await sleep(1500);
            await gotoPage(page, pg);
            await sleep(1200);
          }
        } else if (staleOnes.length === 0) {
          console.log('  ✅ 复查通过，第 ' + pg + ' 页已无「审核通过」残留');
        }
      } else if (pageNumResults.length === 0) {
        console.log('  ℹ️ 第 ' + pg + ' 页本就无「审核通过」，跳过');
      }
    }

    // D. 汇总
    const okN = allResults.filter(r => r.status === 'OK').length;
    const failN = allResults.filter(r => r.status === 'FAIL').length;
    const skipN = allResults.filter(r => r.status === 'SKIP').length;
    const unkN = allResults.filter(r => r.status === 'UNKNOWN').length;
    const dryN = allResults.filter(r => r.status === 'DRY_RUN').length;

    fs.writeFileSync(OUT_FILE, JSON.stringify({ summary: { ok: okN, fail: failN, skip: skipN, unknown: unkN, dryRun: dryN }, results: allResults }, null, 2), 'utf-8');

    console.log('\n' + '='.repeat(50));
    console.log('🏁 上架流程完成');
    console.log('='.repeat(50));
    console.log('✅ 成功(OK): ' + okN);
    console.log('❌ 失败(FAIL): ' + failN);
    console.log('⏭️ 跳过(SKIP): ' + skipN);
    console.log('⚠️ 未知(UNKNOWN): ' + unkN);
    if (opts.dryRun) console.log('🟡 dry-run: ' + dryN);
    console.log('📄 详细结果: ' + OUT_FILE);

    await browser.disconnect().catch(() => {});
    console.log('\n（已 disconnect，未关闭浏览器，登录态保留）');
  } catch (e) {
    console.error('❌ 主流程出错:', e);
    try { await page.screenshot({ path: path.join(__dirname, 'screenshot_main_error_' + Date.now() + '.png') }); } catch (_) {}
    fs.writeFileSync(OUT_FILE, JSON.stringify({ error: String(e && e.stack || e), results: allResults }, null, 2), 'utf-8');
    await browser.disconnect().catch(() => {});
    process.exit(1);
  }
})();
