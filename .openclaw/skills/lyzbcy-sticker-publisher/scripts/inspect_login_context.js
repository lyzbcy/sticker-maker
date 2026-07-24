const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const html = await page.content();
  const idx = html.indexOf('账号密码登录');
  console.log(html.slice(Math.max(0, idx - 1200), idx + 1800));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
