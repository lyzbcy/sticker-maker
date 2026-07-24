const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  await page.evaluate(() => {
    const wrap = document.querySelector('.weui-desktop-dialog__wrp');
    const mask = document.querySelector('.weui-desktop-mask');
    if (wrap) wrap.style.display = 'block';
    if (mask) mask.style.display = 'block';
  });
  for (let i = 0; i < 6; i++) {
    await new Promise(r => setTimeout(r, 5000));
    const snap = await page.evaluate(() => ({
      body: (document.body && document.body.innerText || '').slice(0, 300),
      inputs: Array.from(document.querySelectorAll('input')).map(el => ({ type: el.type, placeholder: el.placeholder, value: el.value })),
      loadingCount: document.querySelectorAll('.weui-desktop-loading').length,
      wrapStyle: document.querySelector('.weui-desktop-dialog__wrp')?.getAttribute('style') || ''
    }));
    console.log('T=' + ((i + 1) * 5));
    console.log(JSON.stringify(snap, null, 2));
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
