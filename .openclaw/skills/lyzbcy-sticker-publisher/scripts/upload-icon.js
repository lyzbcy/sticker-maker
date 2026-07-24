// 上传图标脚本
const puppeteer = require('puppeteer-core');
const path = require('path');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function uploadIcon() {
  const browser = await puppeteer.connect({
    browserURL: 'http://127.0.0.1:7109',
  });

  const pages = await browser.pages();
  const page = pages.find(p => p.url().includes('sticker.weixin.qq.com'));
  
  if (!page) {
    console.log('❌ 未找到微信表情页面');
    return;
  }

  console.log('✅ 找到页面:', page.url());

  // 直接用文件输入框上传
  const fileInputs = await page.$$('input[type="file"]');
  console.log('找到', fileInputs.length, '个文件输入框');
  
  // 图标输入框应该是第4个（索引3），accept="image/png"
  if (fileInputs.length >= 4) {
    const iconPath = path.join('E:\\星星布丁\\微信表情包\\周三涵做表情1\\最终版', '开心比耶.png');
    console.log('准备上传图标:', iconPath);
    
    await fileInputs[3].uploadFile(iconPath);
    console.log('✅ 图标已上传');
    
    await sleep(2000);
    
    // 点击提交
    const submitBtns = await page.$$('button');
    for (const btn of submitBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text === '提交') {
        await btn.click();
        console.log('✅ 已点击提交');
        break;
      }
    }
  }

  browser.disconnect();
}

uploadIcon().catch(console.error);
