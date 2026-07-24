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
  });
  await new Promise(r => setTimeout(r, 500));
  const texts = await page.$$eval('span,button,div,a', els => els.map(el => ({
    text: (el.textContent || '').trim(),
    cls: typeof el.className === 'string' ? el.className : '',
    rect: el.getBoundingClientRect().toJSON()
  })).filter(x => x.text === '账号密码登录' || x.text === '扫码登录' || x.text === '登录'));
  console.log('TEXTS=' + JSON.stringify(texts, null, 2));
  const target = await page.evaluateHandle(() => {
    const isVisible = (el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    };
    return Array.from(document.querySelectorAll('span,button,div,a')).find(el => (el.textContent || '').trim() === '账号密码登录' && isVisible(el)) || null;
  });
  const el = target.asElement();
  if (el) {
    const box = await el.boundingBox();
    console.log('BOX=' + JSON.stringify(box));
    if (box) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  }
  await new Promise(r => setTimeout(r, 1000));
  const result = await page.evaluate(() => ({
    body: (document.body && document.body.innerText || '').slice(0, 500),
    inputs: Array.from(document.querySelectorAll('input')).map(el => ({ type: el.type, placeholder: el.placeholder, value: el.value })),
    html: document.querySelector('.weui-desktop-dialog__wrp')?.outerHTML.slice(0, 1200) || ''
  }));
  console.log(JSON.stringify(result, null, 2));
  await browser.disconnect();
})().catch(err => { console.error(err); process.exit(1); });
