const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const scripts = await page.evaluate(() => Array.from(document.scripts).map(s => s.src).filter(Boolean));
  console.log(JSON.stringify(scripts, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
