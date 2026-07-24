const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const data = await page.evaluate(() => {
    const els = [];
    for (const el of document.querySelectorAll('input, span, button, div')) {
      const text = (el.textContent || '').trim();
      const placeholder = el.placeholder || '';
      const type = el.type || '';
      if (!text && !placeholder && !type) continue;
      if (!(text.includes('账号密码登录') || placeholder || type === 'password' || type === 'text' || type === 'email')) continue;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      els.push({
        tag: el.tagName,
        type,
        text,
        placeholder,
        cls: typeof el.className === 'string' ? el.className : '',
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        width: rect.width,
        height: rect.height,
        html: el.outerHTML.slice(0, 300)
      });
    }
    return els;
  });
  console.log(JSON.stringify(data, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
