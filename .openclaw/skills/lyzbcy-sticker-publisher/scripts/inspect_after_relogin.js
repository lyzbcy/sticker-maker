const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const pages = await browser.pages();
  for (const page of pages) {
    if (!page.url().includes('login')) continue;
    console.log('URL=' + page.url());
    console.log('TITLE=' + await page.title());
    const data = await page.evaluate(() => {
      const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      return Array.from(document.querySelectorAll('input,button,a,span,div')).map(el => ({
        tag: el.tagName,
        type: el.type || '',
        text: (el.textContent || '').trim(),
        placeholder: el.placeholder || '',
        cls: typeof el.className === 'string' ? el.className : '',
        visible: isVisible(el)
      })).filter(x => x.visible && (x.text || x.placeholder || x.type)).slice(0, 120);
    });
    console.log(JSON.stringify(data, null, 2));
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
