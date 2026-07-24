const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  if (!page) { console.log('NOLOGIN'); await browser.disconnect(); return; }
  const body = await page.evaluate(() => (document.body?.innerText || '').slice(0, 800));
  const inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(el => ({ type: el.type, placeholder: el.placeholder, value: el.value, rect: el.getBoundingClientRect().toJSON() })));
  const pwd = await page.evaluate(() => Array.from(document.querySelectorAll('span, div, a, button')).map(el => ({ text: (el.textContent || '').trim(), cls: typeof el.className === 'string' ? el.className : '', rect: el.getBoundingClientRect().toJSON(), display: getComputedStyle(el).display, visibility: getComputedStyle(el).visibility })).filter(x => ['账号密码登录','扫码登录','登录'].includes(x.text)).slice(0, 20));
  console.log('URL=' + page.url());
  console.log('BODY=' + body.replace(/\s+/g, ' ').trim());
  console.log('INPUTS=' + JSON.stringify(inputs, null, 2));
  console.log('TEXTS=' + JSON.stringify(pwd, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
