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
    const tab = Array.from(document.querySelectorAll('span,div,a,button')).find(el => (el.textContent || '').trim() === '账号密码登录');
    if (tab) tab.click();
  });
  await new Promise(r => setTimeout(r, 5000));
  const result = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input')).map(el => ({ type: el.type, placeholder: el.placeholder, value: el.value, cls: el.className }));
    return {
      url: location.href,
      body: (document.body && document.body.innerText || '').slice(0, 500),
      inputs,
      wrapStyle: document.querySelector('.weui-desktop-dialog__wrp')?.getAttribute('style') || '',
      maskStyle: document.querySelector('.weui-desktop-mask')?.getAttribute('style') || ''
    };
  });
  console.log(JSON.stringify(result, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
