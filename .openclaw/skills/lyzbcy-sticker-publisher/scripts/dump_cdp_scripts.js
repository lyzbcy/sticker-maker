const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
  const base = process.cwd();
  const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = (await browser.pages()).find(p => p.url().includes('login'));
  const client = await page.target().createCDPSession();
  const scripts = [];
  client.on('Debugger.scriptParsed', evt => {
    if (evt.url && evt.url.includes('mmemoticonweb')) scripts.push({ scriptId: evt.scriptId, url: evt.url });
  });
  await client.send('Debugger.enable');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));
  const latestByUrl = new Map();
  for (const s of scripts) latestByUrl.set(s.url, s.scriptId);
  const picked = Array.from(latestByUrl.entries()).filter(([url]) => /login|index|browser|md5/.test(url)).slice(0, 20);
  for (const [url, scriptId] of picked) {
    try {
      const src = await client.send('Debugger.getScriptSource', { scriptId });
      const file = path.join(base, 'cdp_' + path.basename(url).replace(/[^a-zA-Z0-9._-]/g, '_'));
      fs.writeFileSync(file, src.scriptSource, 'utf8');
      console.log('saved', file, src.scriptSource.length);
    } catch (e) {
      console.log('failed', url, scriptId, e.message);
    }
  }
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
