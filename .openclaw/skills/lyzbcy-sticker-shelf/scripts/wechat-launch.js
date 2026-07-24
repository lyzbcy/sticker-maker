/**
 * wechat-launch.js — 共享模块：启动/连接浏览器 + 自动登录微信表情开放平台
 *
 * 复用 publisher (lyzbcy-sticker-publisher) 的成熟基础设施：
 *   - .browser-data 登录态目录（共享单一登录态，避免重复登录）
 *   - .env 账号密码（WECHAT_STICKER_ACCOUNT + _PASSWORD_ENCODED）
 *
 * 从 publish.js (lyzbcy-sticker-publisher/scripts/publish.js 第 263-650 行) 提取。
 * 提供给本 skill 的 inspect_home.js 和 shelf.js 复用。
 */

const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

// publisher 的目录（.browser-data / .env 都在这里）
const PUBLISHER_SCRIPTS_DIR = path.resolve(
  __dirname, '..', '..', 'lyzbcy-sticker-publisher', 'scripts'
);
const PUBLISHER_BROWSER_DATA = path.join(PUBLISHER_SCRIPTS_DIR, '.browser-data');
const PUBLISHER_ENV = path.join(PUBLISHER_SCRIPTS_DIR, '.env');

const HOME_URL = 'https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index';
const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/**
 * 读取 publisher .env 里的账号密码（密码 Base64 解码）。
 * @returns {{account:string, password:string}}
 */
function loadCredentials() {
  try { require('dotenv').config({ path: PUBLISHER_ENV }); } catch (e) { /* dotenv 缺失忽略 */ }
  const account = process.env.WECHAT_STICKER_ACCOUNT || '';
  const encoded = process.env.WECHAT_STICKER_PASSWORD_ENCODED || '';
  const password = encoded ? Buffer.from(encoded, 'base64').toString('utf8') : '';
  return { account, password };
}

/**
 * 启动或连接 Edge（复用 publisher 的 .browser-data 登录态）。
 * 优先连接已运行的 Edge；连不上再自启动。
 * @returns {Promise<import('puppeteer-core').Browser>}
 */
async function launchBrowser() {
  const userDataDir = PUBLISHER_BROWSER_DATA;
  console.log('✅ 使用 Edge 浏览器（共享 publisher 登录态）');

  // 优先：连接已启动的 Edge
  const devtoolsPath = path.join(userDataDir, 'DevToolsActivePort');
  if (fs.existsSync(devtoolsPath)) {
    for (let attempt = 1; attempt <= 12; attempt++) {
      try {
        const port = fs.readFileSync(devtoolsPath, 'utf-8').split(/\r?\n/)[0].trim();
        if (!port) { await sleep(1000); continue; }
        const browser = await puppeteer.connect({
          browserURL: 'http://127.0.0.1:' + port,
          defaultViewport: null,
          protocolTimeout: 600000,
        });
        console.log('  ✅ 已连接现有 Edge DevTools: ' + port);
        return browser;
      } catch (e) {
        if (attempt % 3 === 0) console.log('  ⏳ 连接重试 ' + attempt + '/12: ' + (e.message.split('\n')[0]));
        await sleep(1000);
      }
    }
    console.log('  ⚠️ 连不上已运行的 Edge，改为自启动...');
  }

  // 回退：自启动 Edge
  try {
    const browser = await puppeteer.launch({
      headless: false,
      defaultViewport: null,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
      executablePath: EDGE_PATH,
      userDataDir: userDataDir,
      protocolTimeout: 600000,
    });
    console.log('  ✅ 已自启动 Edge（共享 publisher 登录态）');
    return browser;
  } catch (launchErr) {
    throw new Error('启动 Edge 失败: ' + launchErr.message + '。可能 Edge 正被 publisher 占用，请先关闭其它 Edge 实例。');
  }
}

/**
 * 在已打开的 page 上确保已登录。若落在登录页则自动用账号密码登录。
 * 直接移植自 publish.js 第 349-650 行。
 * @param {import('puppeteer-core').Page} page
 * @param {{account:string, password:string}} creds
 * @returns {Promise<boolean>} 是否登录成功
 */
async function ensureLogin(page, creds) {
  await sleep(3000);
  await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
  await sleep(2000);
  const currentUrl = page.url();

  if (!currentUrl.includes('login') && !currentUrl.includes('timeout')) {
    console.log('  ✅ 已处于登录状态，跳过登录');
    return true;
  }

  console.log('📍 检测到需要登录...');
  const { account: ACCOUNT, password: PASSWORD } = creds;
  if (!ACCOUNT || !PASSWORD) {
    console.log('  ❌ 未配置账号密码，无法自动登录');
    return false;
  }

  console.log('  🔐 使用保存的账号密码自动登录...');
  await sleep(5000);
  await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
  await sleep(2000);

  // 主路径：直接调登录接口（MD5 密码）
  let directLoginSucceeded = false;
  try {
    const passwordMd5 = crypto.createHash('md5').update(PASSWORD).digest('hex');
    const loginResult = await page.evaluate(async ({ email, pwd }) => {
      const formData = new FormData();
      formData.append('email', email);
      formData.append('pwd', pwd);
      const response = await fetch('/cgi-bin/mmemoticon-bin/login', {
        method: 'POST', body: formData, credentials: 'include',
      });
      return await response.json();
    }, { email: ACCOUNT, pwd: passwordMd5 });

    if (loginResult && loginResult.base_resp && loginResult.base_resp.ret === 0 && loginResult.redirecturl) {
      const redirectUrl = loginResult.redirecturl.startsWith('http')
        ? loginResult.redirecturl
        : new URL(loginResult.redirecturl, 'https://sticker.weixin.qq.com').toString();
      console.log('  ✅ 已通过登录接口完成账号密码登录');
      await page.goto(redirectUrl, { waitUntil: 'networkidle2', timeout: 30000 });
      directLoginSucceeded = true;
    } else {
      console.log('  ⚠️ 登录接口未成功，回退页面流程: ' + JSON.stringify(loginResult));
    }
  } catch (e) {
    console.log('  ⚠️ 登录接口调用失败，回退页面流程: ' + e.message);
  }

  if (!directLoginSucceeded) {
    // 中转页"重新登录"
    const reloginClicked = await page.evaluate(() => {
      const isVisible = (el) => {
        if (!el) return false;
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      };
      const btn = Array.from(document.querySelectorAll('button, a, div, span'))
        .find(el => (el.textContent || '').trim() === '重新登录' && isVisible(el));
      if (!btn) return false;
      btn.click(); return true;
    });
    if (reloginClicked) { console.log('  ✅ 已点击"重新登录"'); await sleep(2500); }

    // 切"账号密码登录" tab
    await sleep(2000);
    const switchPasswordLogin = async ({ forceOpenDialog = false } = {}) => {
      if (forceOpenDialog) {
        await page.evaluate(() => {
          const w = document.querySelector('.weui-desktop-dialog__wrp');
          const m = document.querySelector('.weui-desktop-mask');
          if (w) w.style.display = 'block';
          if (m) m.style.display = 'block';
        });
        await sleep(300);
      }
      const candidates = await page.$$('span, div, a, button');
      for (const el of candidates) {
        const meta = await page.evaluate(node => {
          const s = window.getComputedStyle(node), r = node.getBoundingClientRect();
          return {
            text: (node.textContent || '').trim(),
            visible: s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0,
          };
        }, el);
        if (meta.text !== '账号密码登录' || !meta.visible) continue;
        const box = await el.boundingBox();
        if (box) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        else await el.evaluate(node => node.click());
        return true;
      }
      return false;
    };
    let switched = await switchPasswordLogin();
    if (!switched) {
      console.log('  ⚠️ 常规切换失败，强制显示弹层重试...');
      switched = await switchPasswordLogin({ forceOpenDialog: true });
      await sleep(1000);
    }
    console.log('  ✅ 已切换到账号密码登录');

    // 等输入框就绪
    await sleep(1000);
    await page.waitForFunction(() => {
      const isVisible = (el) => {
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      };
      const t = Array.from(document.querySelectorAll('input')).find(el => ['text', 'email'].includes((el.type || '').toLowerCase()) && isVisible(el));
      const p = Array.from(document.querySelectorAll('input')).find(el => (el.type || '').toLowerCase() === 'password' && isVisible(el));
      return !!(t && p);
    }, { timeout: 30000 }).catch(() => {});
    await sleep(1000);

    // 找可见输入框填表
    const inputs = await page.$$('input');
    let accountInput = null, passwordInput = null;
    for (const input of inputs) {
      const meta = await page.evaluate(el => {
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        return { type: (el.type || '').toLowerCase(), visible: s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0 };
      }, input);
      if (!meta.visible) continue;
      if (!accountInput && (meta.type === 'text' || meta.type === 'email')) { accountInput = input; continue; }
      if (!passwordInput && meta.type === 'password') { passwordInput = input; }
    }
    if (!accountInput || !passwordInput) {
      await page.screenshot({ path: path.join(__dirname, 'login_form_debug.png') });
      console.log('  ❌ 未找到可见账号/密码输入框');
      return false;
    }
    await accountInput.click({ clickCount: 3 }); await page.keyboard.press('Backspace');
    await accountInput.type(ACCOUNT, { delay: 50 });
    await passwordInput.click({ clickCount: 3 }); await page.keyboard.press('Backspace');
    await passwordInput.type(PASSWORD, { delay: 50 });
    console.log('  ✅ 账号密码已填写');
    await sleep(2000);

    // 点登录按钮（物理坐标）
    try {
      const loginBtn = await page.evaluateHandle(() => {
        const isVisible = (el) => {
          const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
          return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        };
        const btns = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
        return btns.find(el => {
          const text = ((el.textContent || el.value || '')).trim();
          const disabled = !!el.disabled || el.getAttribute('aria-disabled') === 'true';
          return text === '登录' && isVisible(el) && !disabled;
        }) || null;
      });
      const btnEl = loginBtn.asElement();
      if (btnEl) {
        const box = await btnEl.boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await sleep(120); await page.mouse.down(); await sleep(120); await page.mouse.up();
          console.log('  ✅ 已点击"登录"按钮');
        }
        await sleep(1200);
        if (page.url().includes('login')) { await page.keyboard.press('Enter'); console.log('  ✅ 回车兜底'); }
      } else {
        console.log('  ⚠️ 未找到可见"登录"按钮');
      }
    } catch (e) { console.log('  ❌ 点击登录按钮出错: ' + e.message); }
  }

  // 等登录完成（URL + 文案双重检测，最多 3 分钟）
  console.log('  ⏳ 等待登录完成（最多3分钟）...');
  await sleep(3000);
  for (let i = 0; i < 36; i++) {
    await sleep(5000);
    const url = page.url();
    const bodyText = await page.evaluate(() => document.body ? document.body.innerText : '');
    if (!url.includes('login') || bodyText.includes('提交作品') || bodyText.includes('我的表情')) {
      console.log('  ✅ 登录成功！');
      await sleep(2000);
      return true;
    }
    // 错误检测
    const loginError = await page.evaluate(() => {
      const isVisible = (el) => {
        const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || '1') > 0.5 && r.width > 0 && r.height > 0;
      };
      return Array.from(document.querySelectorAll('body *')).some(el => {
        const t = (el.textContent || '').trim();
        const leaf = t.length < 80 && Array.from(el.children || []).every(c => !(c.textContent || '').trim());
        return isVisible(el) && leaf && (t.includes('账号或密码错误') || t.includes('验证码'));
      });
    });
    if (loginError) { console.log('  ❌ 登录失败（账号密码错误或需验证码）'); return false; }
    if (i % 6 === 5) console.log('  ⏳ 仍在等待... (' + ((i + 1) * 5) + 's)');
  }
  await page.screenshot({ path: path.join(__dirname, 'login_debug.png') });
  console.log('  ❌ 登录超时');
  return false;
}

module.exports = {
  PUBLISHER_BROWSER_DATA, PUBLISHER_ENV, HOME_URL, EDGE_PATH,
  sleep, loadCredentials, launchBrowser, ensureLogin,
};
