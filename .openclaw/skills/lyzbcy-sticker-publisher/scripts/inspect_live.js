const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const portFile = path.join(base, '.browser-data', 'DevToolsActivePort');
  const port = fs.readFileSync(portFile, 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const pages = await browser.pages();
  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    let body = '';
    try {
      body = await page.evaluate(() => (document.body && document.body.innerText || '').slice(0, 800));
    } catch (e) {
      body = '[unavailable]';
    }
    console.log('---PAGE ' + i + '---');
    console.log('URL:', page.url());
    console.log('TITLE:', await page.title());
    console.log('BODY:', body.replace(/\s+/g, ' ').trim());
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
