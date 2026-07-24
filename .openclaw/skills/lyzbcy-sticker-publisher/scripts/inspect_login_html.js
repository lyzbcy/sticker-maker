const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const html = await page.content();
  for (const needle of ['账号密码登录', '扫码登录', 'login', 'relogin', 'timeout']) {
    const idx = html.indexOf(needle);
    console.log('NEEDLE=' + needle + ' IDX=' + idx);
    if (idx >= 0) {
      console.log(html.slice(Math.max(0, idx - 200), idx + 400));
      console.log('---');
    }
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
