const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const html = await page.content();
  fs.writeFileSync(path.join(base, 'timeout_login_page.html'), html, 'utf8');
  const scripts = await page.evaluate(() => Array.from(document.querySelectorAll('link[rel="modulepreload"], script[src]')).map(el => el.href || el.src).filter(Boolean));
  console.log(JSON.stringify(scripts, null, 2));
  for (const [i, url] of scripts.slice(0, 8).entries()) {
    try {
      const text = await page.evaluate(async (u) => {
        const res = await fetch(u, { credentials: 'include' });
        return await res.text();
      }, url);
      fs.writeFileSync(path.join(base, `bundle_${i}.js`), text, 'utf8');
      console.log('saved', i, url, text.length);
    } catch (e) {
      console.log('failed', i, url, e.message);
    }
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
