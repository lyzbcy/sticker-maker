const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const info = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button, a, div, span')).find(el => (el.textContent || '').trim() === '重新登录');
    if (!btn) return null;
    const attrs = {};
    for (const name of btn.getAttributeNames()) attrs[name] = btn.getAttribute(name);
    const rect = btn.getBoundingClientRect();
    return {
      tag: btn.tagName,
      text: btn.textContent.trim(),
      className: btn.className,
      attrs,
      onclickType: typeof btn.onclick,
      html: btn.outerHTML,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
