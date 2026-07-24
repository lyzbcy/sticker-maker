const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const pages = await browser.pages();
  const page = pages.find(p => p.url().includes('login'));
  const data = await page.evaluate(() => {
    const rows = [];
    for (const el of document.querySelectorAll('a,button,span,div')) {
      const text = (el.textContent || '').trim();
      if (!text || text.length > 30) continue;
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      if (!visible) continue;
      rows.push({ tag: el.tagName, text, cls: el.className || '', x: rect.x, y: rect.y, w: rect.width, h: rect.height });
    }
    return rows.slice(0, 80);
  });
  console.log(JSON.stringify(data, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
