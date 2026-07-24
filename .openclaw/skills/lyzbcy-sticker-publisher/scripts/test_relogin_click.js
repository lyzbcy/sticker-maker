const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const btn = await page.$('button.weui-desktop-btn_primary');
  if (!btn) throw new Error('button not found');
  const box = await btn.boundingBox();
  console.log('BEFORE=' + page.url());
  if (box) {
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await new Promise(r => setTimeout(r, 3000));
  }
  console.log('AFTER=' + page.url());
  console.log('TITLE=' + await page.title());
  const body = await page.evaluate(() => (document.body && document.body.innerText || '').slice(0, 500));
  console.log('BODY=' + body.replace(/\s+/g, ' ').trim());
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
