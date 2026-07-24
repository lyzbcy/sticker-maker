const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
(async () => {
 const base = process.cwd();
 const port = fs.readFileSync(path.join(base, '.browser-data', 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
 const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
 const pages = await browser.pages();
 for (let i=0;i<pages.length;i++) {
  const p = pages[i];
  let data = {};
  try { data = await p.evaluate(() => ({ body:(document.body?.innerText||'').slice(0,800), inputs:Array.from(document.querySelectorAll('input')).map(el=>({type:el.type,placeholder:el.placeholder,value:el.value,rect:el.getBoundingClientRect().toJSON()})), buttons:Array.from(document.querySelectorAll('button,div,span')).map(el=>({text:(el.textContent||'').trim(), cls: typeof el.className==='string'?el.className:'', rect:el.getBoundingClientRect().toJSON(), display:getComputedStyle(el).display, visibility:getComputedStyle(el).visibility})).filter(x=>['登录','账号密码登录','扫码登录','重新登录'].includes(x.text)).slice(0,30)})); } catch(e) { data={err:e.message}; }
  console.log('PAGE', i, p.url(), await p.title(), JSON.stringify(data, null, 2));
 }
 await browser.disconnect();
})().catch(e=>{console.error(e); process.exit(1);});
