// 补传图标脚本
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function uploadIcon(targetDir) {
  // 读取 DevTools 端口
  const portPath = path.join(__dirname, '.browser-data', 'DevToolsActivePort');
  const port = fs.readFileSync(portPath, 'utf8').split('\n')[0].trim();
  console.log('Connecting to browser at port:', port);

  const browser = await puppeteer.connect({
    browserURL: 'http://127.0.0.1:' + port,
    defaultViewport: null,
  });

  const pages = await browser.pages();
  const page = pages.find(p => p.url().includes('sticker.weixin.qq.com'));
  
  if (!page) {
    console.log('No sticker page found');
    await browser.disconnect();
    return;
  }

  console.log('Found page:', page.url().substring(0, 80));

  // 自动检测图片目录
  let imageDir = targetDir;
  const finalDir = path.join(targetDir, '最终版');
  const chromaKeyDir = path.join(targetDir, '原图_透明ChromaKey');
  if (fs.existsSync(finalDir)) {
    imageDir = finalDir;
  } else if (fs.existsSync(chromaKeyDir)) {
    imageDir = chromaKeyDir;
  }

  // 选一张人物占比大的做图标
  const images = fs.readdirSync(imageDir).filter(f => /\.(png|PNG)$/.test(f) && !f.startsWith('.'));
  if (images.length === 0) {
    console.log('No images found in', imageDir);
    await browser.disconnect();
    return;
  }
  const iconPath = path.join(imageDir, images[0]);

  // Find the icon upload input (4th file input, index 3)
  const fileInputs = await page.$$('input[type="file"]');
  console.log('File inputs found:', fileInputs.length);
  
  if (fileInputs.length >= 4) {
    console.log('Uploading icon:', iconPath);
    try {
      await fileInputs[3].uploadFile(iconPath);
      console.log('Icon uploaded!');
      await sleep(3000);
      
      // Try clicking submit again
      const buttons = await page.$$('button');
      for (const btn of buttons) {
        const text = await page.evaluate(el => el.textContent, btn);
        if (text && text.includes('提交')) {
          await btn.click();
          console.log('Clicked submit!');
          break;
        }
      }
    } catch (e) {
      console.log('Icon upload failed:', e.message);
    }
  }

  await browser.disconnect();
}

const targetDir = process.argv[2] || 'E:\\星星布丁\\微信表情包\\周三涵做表情4';
uploadIcon(targetDir).catch(err => { console.error(err); process.exit(1); });
