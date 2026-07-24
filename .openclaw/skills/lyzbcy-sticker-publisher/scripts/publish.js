const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

// 加载环境变量（如果存在.env文件）
try {
  require('dotenv').config({ path: path.join(__dirname, '.env') });
} catch (e) {
  // dotenv未安装或.env文件不存在，忽略
}

/**
 * 微信表情包发布脚本 (Puppeteer 版)
 * 严格按照既定发布流程执行，不得省略或改序
 */

const FIXED_CONFIG = {
  copyright: '捞鱼真不吃鱼',
  appreciationText: '谢谢你喜欢我~',
  appreciationGuideImg: 'E:\\星星布丁\\微信表情包\\赞赏页\\赞赏引导图.png',
  appreciationThanksImg: 'E:\\星星布丁\\微信表情包\\赞赏页\\赞赏致谢图.png',
  typeCategory: '卡通表情/其他',       // value="1"
  styles: ['软萌可爱', '日常'],
  theme: '万能通用',
  region: 'DEF',                        // 全球
};

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function readCharacterCard(dir) {
  const cardPath = path.join(dir, '本次制作角色.md');
  if (!fs.existsSync(cardPath)) {
    console.log('  ⚠️  未找到 本次制作角色.md，默认使用「人物合辑」');
    return { hasLaoyu: true, onlyLaoyu: false, roleTarget: '人物合辑' };
  }
  const content = fs.readFileSync(cardPath, 'utf-8');
  const onlyLaoyu = /只含捞鱼[：:]\s*是/.test(content) || /角色分类[：:]\s*男人/.test(content);
  const hasLaoyu = /含捞鱼[：:]\s*是/.test(content) || onlyLaoyu;
  
  let roleTarget = '女人';
  if (onlyLaoyu) {
    roleTarget = '男人';
  } else if (hasLaoyu) {
    roleTarget = '人物合辑';
  }
  
  console.log(`  📋 角色卡: 只含捞鱼=${onlyLaoyu ? '是' : '否'}, 含捞鱼=${hasLaoyu ? '是' : '否'} → 角色选择为「${roleTarget}」`);
  return { hasLaoyu, onlyLaoyu, roleTarget };
}

/**
 * 从文件名提取含义词
 */
function extractMeaning(filename) {
  let name = path.basename(filename, path.extname(filename));
  // 如果文件名是 "1-开心" 格式，取最后一部分
  if (name.includes('-')) {
    name = name.split('-').pop();
  }
  return name.trim();
}

function runPrePublishValidation(dir) {
  const validateScript = path.resolve(
    __dirname,
    '..',
    '..',
    'lyzbcy-sticker-creator',
    'scripts',
    'validate.py'
  );

  console.log('🧪 运行发布前校验...');
  const result = spawnSync('python', [validateScript, '--dir', dir, '--stage', 'pre_publish'], {
    encoding: 'utf-8',
    stdio: 'pipe',
  });

  if (result.stdout) {
    console.log(result.stdout.trim());
  }
  if (result.stderr) {
    console.error(result.stderr.trim());
  }
  if (result.error) {
    throw new Error(`无法执行 validate.py: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error('发布前校验未通过，已中止发布');
  }

  console.log('✅ 发布前校验通过，继续发布流程');
}

function normalizeDescriptionText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function buildFallbackDescription(themeDesc) {
  const theme = normalizeDescriptionText(themeDesc || '日常聊天');
  return normalizeDescriptionText('这组表情主打' + theme + '，把可爱反应装进聊天，开心、撒娇、犯困都能接住。');
}

function readStickerDescription(dir, themeDesc) {
  const candidates = ['介绍.txt', '表情介绍.txt', 'description.txt'];
  for (const filename of candidates) {
    const descPath = path.join(dir, filename);
    if (!fs.existsSync(descPath)) {
      continue;
    }
    const desc = normalizeDescriptionText(fs.readFileSync(descPath, 'utf-8'));
    if (!desc) {
      throw new Error(filename + ' 为空，请填写 1-80 字的表情介绍');
    }
    if ([...desc].length > 80) {
      throw new Error(filename + ' 超过 80 字：当前 ' + [...desc].length + ' 字');
    }
    console.log('  📝 使用自定义介绍: ' + filename + '（' + [...desc].length + '/80）');
    return desc;
  }

  const fallback = buildFallbackDescription(themeDesc);
  if ([...fallback].length > 80) {
    throw new Error('默认介绍超过 80 字：当前 ' + [...fallback].length + ' 字');
  }
  console.log('  📝 使用默认短介绍（' + [...fallback].length + '/80）');
  return fallback;
}

async function publishSticker(options) {
  const {
    name,       // e.g. 周三涵做表情1
    dir,        // e.g. E:\星星布丁\微信表情包\周三涵做表情1
    type,       // 'static' or 'dynamic'
    theme_idea, // 介绍中的主题思想，默认"日常交流"
  } = options;

  const themeDesc = theme_idea || '日常交流';
  const stickerDescription = readStickerDescription(dir, themeDesc);

  runPrePublishValidation(dir);

  // 自动检测图片目录：优先使用"最终版"，其次"原图_透明ChromaKey"，最后根目录
  let imageDir = dir;
  const finalDir = path.join(dir, '最终版');
  const chromaKeyDir = path.join(dir, '原图_透明ChromaKey');
  
  if (fs.existsSync(finalDir)) {
    imageDir = finalDir;
    console.log('📁 使用"最终版"目录');
  } else if (fs.existsSync(chromaKeyDir)) {
    imageDir = chromaKeyDir;
    console.log('📁 使用"原图_透明ChromaKey"目录');
  }

  // 扫描图片目录
  const exts = type === 'static' ? ['.png', '.PNG'] : ['.gif', '.GIF'];
  const allFiles = fs.readdirSync(imageDir).filter(f => exts.includes(path.extname(f)));
  const imageFiles = allFiles.filter(f => !f.startsWith('.')); // 排除隐藏文件

  // 按故事线顺序排序：优先用 原图/_meaning_map.json 的 key(1-16) 顺序
  // （多故事架构下，key1-4=故事A，5-8=故事B…，按此顺序上传，微信面板里故事表情就连着排）
  const meaningMapPath = path.join(dir, '原图', '_meaning_map.json');
  let storyOrder = null;
  try {
    if (fs.existsSync(meaningMapPath)) {
      const rawMap = JSON.parse(fs.readFileSync(meaningMapPath, 'utf-8'));
      // key 按数字升序 → 得到含义词的故事线序列
      storyOrder = Object.keys(rawMap)
        .map(k => parseInt(k, 10))
        .sort((a, b) => a - b)
        .map(k => rawMap[String(k)]);
      console.log(`📖 读到故事线顺序 (_meaning_map.json)，${storyOrder.length} 张按故事线排序上传`);
    }
  } catch (e) {
    console.log(`⚠️ 读取 _meaning_map.json 失败，按文件名排序: ${e.message}`);
  }

  if (storyOrder && storyOrder.length > 0) {
    // 按故事线顺序排；文件名 = 含义词 + 后缀，不在 map 里的回退排到末尾(按字母序)
    const orderIndex = new Map(storyOrder.map((cn, i) => [cn, i]));
    imageFiles.sort((a, b) => {
      const aStem = path.parse(a).name;
      const bStem = path.parse(b).name;
      const ai = orderIndex.has(aStem) ? orderIndex.get(aStem) : 9999;
      const bi = orderIndex.has(bStem) ? orderIndex.get(bStem) : 9999;
      if (ai !== bi) return ai - bi;
      return aStem.localeCompare(bStem, 'zh');
    });
    console.log('   排序后上传顺序(故事线):', imageFiles.map(f => path.parse(f).name).join(' → '));
  } else {
    imageFiles.sort((a, b) => path.parse(a).name.localeCompare(path.parse(b).name, 'zh'));
    console.log('   按(中文)文件名排序上传');
  }

  if (imageFiles.length === 0) {
    console.error('❌ 未找到表情图片文件！目录:', imageDir);
    return;
  }
  console.log(`📁 找到 ${imageFiles.length} 张表情图片`);

  // 读取角色卡，决定步骤15的角色选择
  const charCard = readCharacterCard(dir);

  // 含义词列表（从文件名推导）
  const meanings = imageFiles.map(f => extractMeaning(f));

  // ===== 横幅/封面/图标路径检测 ⭐ =====
  // 优先级：专用文件夹 > 自动选择
  
  // 横幅（横幅/ 文件夹 > 自动选图）
  const bannerDir = path.join(dir, '横幅');
  let bannerPath;
  if (fs.existsSync(bannerDir)) {
    const bannerFiles = fs.readdirSync(bannerDir).filter(f => /\.(png|jpg|jpeg)$/i.test(f) && !f.startsWith('.'));
    if (bannerFiles.length > 0) {
      bannerPath = path.join(bannerDir, bannerFiles[0]);
      console.log('🖼️  横幅: 使用 横幅/ 文件夹');
    }
  }
  if (!bannerPath) {
    bannerPath = path.join(imageDir, imageFiles[0]);
    console.log('⚠️  横幅: 未找到专用横幅，使用第一张表情图');
  }

  // 封面（封面/ 文件夹 > 尽量与横幅同图 > 自动选图）
  const coverDir = path.join(dir, '封面');
  let coverPath;
  if (fs.existsSync(coverDir)) {
    const coverFiles = fs.readdirSync(coverDir).filter(f => /\.png$/i.test(f) && !f.startsWith('.'));
    if (coverFiles.length > 0) {
      coverPath = path.join(coverDir, coverFiles[0]);
      console.log('🖼️  封面: 使用 封面/ 文件夹');
    }
  }
  if (!coverPath) {
    // 回退：与横幅同图
    coverPath = bannerPath;
    console.log('⚠️  封面: 未找到专用封面，使用横幅图');
  }

  // 图标（图标/ 文件夹 > 自动选图）
  const iconDir = path.join(dir, '图标');
  let iconPath;
  if (fs.existsSync(iconDir)) {
    const iconFiles = fs.readdirSync(iconDir).filter(f => /\.png$/i.test(f) && !f.startsWith('.'));
    if (iconFiles.length > 0) {
      iconPath = path.join(iconDir, iconFiles[0]);
      console.log('🖼️  图标: 使用 图标/ 文件夹');
    }
  }
  if (!iconPath) {
    iconPath = path.join(imageDir, imageFiles[0]);
    console.log('⚠️  图标: 未找到专用图标，使用第一张表情图');
  }

  console.log('🚀 开始自动化发布表情包...');

  // 持久化用户数据目录，保存登录状态
  const userDataDir = path.join(__dirname, '.browser-data');
  
  // 从环境变量读取账号密码（密码Base64编码）
  const ACCOUNT = process.env.WECHAT_STICKER_ACCOUNT || '';
  const PASSWORD_ENCODED = process.env.WECHAT_STICKER_PASSWORD_ENCODED || '';
  const PASSWORD = PASSWORD_ENCODED ? Buffer.from(PASSWORD_ENCODED, 'base64').toString('utf8') : '';

  // 使用Edge浏览器（Windows自带）
  const executablePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  console.log('✅ 使用Edge浏览器（登录状态会自动保存）');

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: false,
      defaultViewport: null,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
      executablePath: executablePath,
      userDataDir: userDataDir,
      protocolTimeout: 600000, // 10分钟超时
    });
  } catch (launchError) {
    console.log('  ⚠️ launch() 未接上浏览器，尝试连接已启动的 Edge...');
    const devtoolsPath = path.join(userDataDir, 'DevToolsActivePort');
    let lastConnectError = launchError;
    for (let attempt = 1; attempt <= 12; attempt++) {
      await sleep(1000);
      if (!fs.existsSync(devtoolsPath)) {
        continue;
      }
      const port = fs.readFileSync(devtoolsPath, 'utf-8').split('\n')[0].trim();
      if (!port) {
        continue;
      }
      try {
        browser = await puppeteer.connect({
          browserURL: 'http://127.0.0.1:' + port,
          defaultViewport: null,
          protocolTimeout: 600000,
        });
        console.log('  ✅ 已连接现有 Edge DevTools: ' + port);
        break;
      } catch (connectError) {
        lastConnectError = connectError;
        console.log('  ⏳ DevTools 端口暂不可用，重试 ' + attempt + '/12: ' + port);
      }
    }
    if (!browser) {
      throw lastConnectError;
    }
  }

  const page = await browser.newPage();
  page.setDefaultTimeout(300000); // 5分钟页面级超时

  try {
    // ========== 步骤1：打开登录页 ==========
    console.log('📍 步骤1：打开平台首页...');
    // 微信平台会做服务端重定向，networkidle2 容易 frame detach，改用 domcontentloaded
    let gotoSuccess = false;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await page.goto('https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index', {
          waitUntil: 'domcontentloaded',
          timeout: 30000,
        });
        gotoSuccess = true;
        break;
      } catch (e) {
        console.log(`  ⚠️ goto 失败 (第${attempt + 1}次): ${e.message}`);
        if (attempt < 2) {
          // 重建 page 再试
          await page.close().catch(() => {});
          page = await browser.newPage();
          page.setDefaultTimeout(300000);
          await sleep(3000);
        }
      }
    }
    if (!gotoSuccess) throw new Error('3次重试后仍无法打开首页');

    // 等待登录页完全加载
    await sleep(3000);
    await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
    await sleep(2000);
    const currentUrl = page.url();

    if (currentUrl.includes('/pages/timeout/login') || currentUrl.includes('login')) {
      // ========== 步骤2：账号密码登录 ==========
      console.log('📍 步骤2：检测到需要登录...');
      
      if (ACCOUNT && PASSWORD) {
        // 自动登录
        console.log('  🔐 使用保存的账号密码自动登录...');
        // 等待登录页完全稳定（避免 frame detach）
        await sleep(5000);
        await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
        await sleep(2000);

        let directLoginSucceeded = false;
        try {
          const passwordMd5 = crypto.createHash('md5').update(PASSWORD).digest('hex');
          const loginResult = await page.evaluate(async ({ email, pwd }) => {
            const formData = new FormData();
            formData.append('email', email);
            formData.append('pwd', pwd);
            const response = await fetch('/cgi-bin/mmemoticon-bin/login', {
              method: 'POST',
              body: formData,
              credentials: 'include',
            });
            return await response.json();
          }, { email: ACCOUNT, pwd: passwordMd5 });

          if (loginResult?.base_resp?.ret === 0 && loginResult.redirecturl) {
            const redirectUrl = loginResult.redirecturl.startsWith('http')
              ? loginResult.redirecturl
              : new URL(loginResult.redirecturl, 'https://sticker.weixin.qq.com').toString();
            console.log('  ✅ 已通过登录接口完成账号密码登录');
            await page.goto(redirectUrl, { waitUntil: 'networkidle2', timeout: 30000 });
            directLoginSucceeded = true;
          } else {
            console.log('  ⚠️ 登录接口未成功，回退到页面按钮流程: ' + JSON.stringify(loginResult));
          }
        } catch (e) {
          console.log('  ⚠️ 登录接口调用失败，回退到页面按钮流程: ' + e.message);
        }

        if (!directLoginSucceeded) {
          // 某些场景会先落在“登录超时，请重新登录”中转页，要先点“重新登录”进入真正的登录表单
          const reloginClicked = await page.evaluate(() => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 0 &&
              rect.height > 0;
          };

          const buttons = Array.from(document.querySelectorAll('button, a, div, span'));
          const reloginBtn = buttons.find(el => {
            const text = (el.textContent || '').trim();
            return text === '重新登录' && isVisible(el);
          });

          if (!reloginBtn) return false;
          reloginBtn.click();
          return true;
          });
          if (reloginClicked) {
            console.log('  ✅ 已点击“重新登录”入口');
            await sleep(2500);
          }
        
        // 点击"账号密码登录" tab；若超时页未正常拉起弹层，则强制显示隐藏弹层再切换
        await sleep(2000);
        const switchPasswordLogin = async ({ forceOpenDialog = false } = {}) => {
          if (forceOpenDialog) {
            await page.evaluate(() => {
              const dialogWrap = document.querySelector('.weui-desktop-dialog__wrp');
              const dialogMask = document.querySelector('.weui-desktop-mask');
              if (dialogWrap) dialogWrap.style.display = 'block';
              if (dialogMask) dialogMask.style.display = 'block';
            });
            await sleep(300);
          }

          const candidates = await page.$$('span, div, a, button');
          for (const el of candidates) {
            const meta = await page.evaluate(node => {
              const style = window.getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return {
                text: (node.textContent || '').trim(),
                visible: style.display !== 'none' &&
                  style.visibility !== 'hidden' &&
                  rect.width > 0 &&
                  rect.height > 0,
              };
            }, el);

            if (meta.text !== '账号密码登录' || !meta.visible) continue;

            const box = await el.boundingBox();
            if (box) {
              await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
            } else {
              await el.evaluate(node => node.click());
            }
            return true;
          }

          return false;
        };

        let switchedToPasswordLogin = await switchPasswordLogin();
        if (!switchedToPasswordLogin) {
          console.log('  ⚠️ 常规方式未拉起账号密码登录，尝试强制显示隐藏弹层...');
          switchedToPasswordLogin = await switchPasswordLogin({ forceOpenDialog: true });
          await sleep(1000);
        }

        console.log('  ✅ 已切换到账号密码登录');
        
        // 🔴 等输入框真正渲染出来
        await sleep(1000);
        const visibleLoginFormReady = await page.waitForFunction(() => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              rect.width > 0 &&
              rect.height > 0;
          };
          const textInput = Array.from(document.querySelectorAll('input')).find(
            el => ['text', 'email'].includes((el.type || '').toLowerCase()) && isVisible(el)
          );
          const passwordInput = Array.from(document.querySelectorAll('input')).find(
            el => (el.type || '').toLowerCase() === 'password' && isVisible(el)
          );
          return !!textInput && !!passwordInput;
        }, { timeout: 30000 }).then(() => true).catch(() => false);
        if (!visibleLoginFormReady) {
          await page.screenshot({ path: require('path').join(__dirname, 'login_form_debug.png') });
          throw new Error('未找到可见的账号密码登录表单');
        }
        console.log('  ✅ 输入框已就绪');
        await sleep(1000);
        
        // 🔴 只对可见的账号/密码框输入，避免命中隐藏表单
        const visibleInputs = await page.$$('input');
        let accountInput = null;
        let passwordInput = null;
        for (const input of visibleInputs) {
          const meta = await page.evaluate(el => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return {
              type: (el.type || '').toLowerCase(),
              visible: style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0,
            };
          }, input);

          if (!meta.visible) continue;
          if (!accountInput && (meta.type === 'text' || meta.type === 'email')) {
            accountInput = input;
            continue;
          }
          if (!passwordInput && meta.type === 'password') {
            passwordInput = input;
          }
        }

        if (!accountInput || !passwordInput) {
          throw new Error('未找到可见的账号/密码输入框');
        }

        await accountInput.click({ clickCount: 3 });
        await page.keyboard.press('Backspace');
        await accountInput.type(ACCOUNT, { delay: 50 });

        await passwordInput.click({ clickCount: 3 });
        await page.keyboard.press('Backspace');
        await passwordInput.type(PASSWORD, { delay: 50 });
        console.log('  ✅ 账号密码已填写');
        
        await sleep(2000);
        
        // 🔴 先尝试精确点击可见的“登录”按钮，再回车兜底
        try {
          const loginBtn = await page.evaluateHandle(() => {
            const isVisible = (el) => {
              if (!el) return false;
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              return style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0;
            };

            const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
            return buttons.find(el => {
              const text = ((el.textContent || el.value || '')).trim();
              const disabled = !!el.disabled || el.getAttribute('aria-disabled') === 'true';
              return text === '登录' && isVisible(el) && !disabled;
            }) || null;
          });

          const loginBtnEl = loginBtn.asElement();
          if (!loginBtnEl) {
            throw new Error('未找到可见且可点击的“登录”按钮');
          }

          const box = await loginBtnEl.boundingBox();
          if (!box) {
            throw new Error('“登录”按钮没有可点击坐标');
          }
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await sleep(120);
          await page.mouse.down();
          await sleep(120);
          await page.mouse.up();
          console.log('  ✅ 已使用物理坐标点击可见的“登录”按钮');

          await sleep(1200);
          if (page.url().includes('login')) {
            await page.keyboard.press('Enter');
            console.log('  ✅ 已额外按回车兜底');
          }
        } catch (e) {
          console.log('  ❌ 点击登录按钮出错: ' + e.message);
        }
        }
      } else {
        console.log('  ⚠️ 未保存账号密码，请手动登录');
      }
      
      // 等待登录完成（检查URL跳转或页面内容变化）
      console.log('  ⏳ 等待登录完成（最多3分钟）...');
      
      // 先等2秒看页面反应
      await sleep(3000);
      
      // 🔴 同时检测URL变化和页面内容
      let loginSuccess = false;
      for (let i = 0; i < 36; i++) { // 36次 × 5秒 = 3分钟
        await sleep(5000);
        const url = page.url();
        const bodyText = await page.evaluate(() => document.body?.innerText || '');
        
        // 登录成功的标志
        if (!url.includes('login') || bodyText.includes('提交作品') || bodyText.includes('我的表情')) {
          console.log(`  ✅ 登录成功！(url: ${url.includes('login') ? 'login page' : 'not login page'}, body has keywords: ${bodyText.includes('提交作品') || bodyText.includes('我的表情')})`);
          loginSuccess = true;
          break;
        }
        
        // 检测是否有错误提示
        const visibleLoginError = await page.evaluate(() => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const opacity = Number(style.opacity || '1');
            return style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              opacity > 0.5 &&
              rect.width > 0 &&
              rect.height > 0;
          };
          return Array.from(document.querySelectorAll('body *')).some(el => {
            const text = (el.textContent || '').trim();
            const isLeafText = text.length < 80 &&
              Array.from(el.children || []).every(child => !(child.textContent || '').trim());
            return isVisible(el) && isLeafText && (text.includes('账号或密码错误') || text.includes('验证码'));
          });
        });
        if (visibleLoginError) {
          console.log(`  ❌ 登录失败: ${bodyText.substring(0, 200)}`);
          break;
        }
        
        if (i % 6 === 5) {
          console.log(`  ⏳ 仍在等待... (${(i+1)*5}s)`);
        }
      }
      
      if (!loginSuccess) {
        // 截图debug
        await page.screenshot({ path: require('path').join(__dirname, 'login_debug.png') });
        console.log('  📸 已保存登录页面截图: login_debug.png');
        throw new Error('登录超时——请检查账号密码是否正确、是否需要验证码');
      }
      
      console.log('  ✅ 登录成功！');
      await sleep(2000);
    } else {
      console.log('  ✅ 已处于登录状态，跳过登录步骤');
    }

    // ========== 步骤3：点击"提交作品" ==========
    console.log('📍 步骤3：点击"提交作品"...');
    await sleep(2000);
    // 微信平台 SPA 跳转会 detach frame，用 waitForNavigation 保持同步
    let submitWorksBtns = [];
    try {
      submitWorksBtns = await page.$$('button.weui-desktop-btn_primary');
    } catch (e) {
      console.log(`  ⚠️ frame detached, 等待重连...`);
      await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
      await sleep(2000);
      await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
      submitWorksBtns = await page.$$('button.weui-desktop-btn_primary');
    }
    let submitClicked = false;
    for (const btn of submitWorksBtns) {
      try {
        const text = await page.evaluate(el => el.textContent.trim(), btn);
        if (text.includes('提交作品')) {
          await btn.click();
          console.log('  ✅ 已点击"提交作品"');
          submitClicked = true;
          break;
        }
      } catch (e) {
        // frame detached during click, ignore and wait for navigation
      }
    }
    if (submitClicked) {
      await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
      await sleep(3000);
      await page.waitForSelector('body', { timeout: 10000 }).catch(() => {});
    }

    // ========== 步骤4：点击"表情专辑" ==========
    console.log('📍 步骤4：选择"表情专辑"...');
    await page.waitForSelector('a.submit-stiker__type-list-item__container', { timeout: 10000 });
    const albumLinks = await page.$$('a.submit-stiker__type-list-item__container');
    for (const link of albumLinks) {
      const text = await page.evaluate(el => el.textContent.trim(), link);
      if (text.includes('表情专辑')) {
        await link.click();
        console.log('  ✅ 已点击"表情专辑"');
        break;
      }
    }

    await sleep(3000);

    // ========== 步骤5：选择表情类型 ==========
    if (type === 'static') {
      console.log('📍 步骤5：选择静态表情类型...');
      const radios = await page.$$('i.weui-desktop-icon-radio');
      if (radios.length > 0) {
        await radios[0].click();
        console.log('  ✅ 已选择静态表情');
      }
    } else {
      console.log('📍 步骤5：保持动态表情类型');
    }

    await sleep(1000);

    // ========== 步骤6：上传图标（提前做，避免后续元素遮挡） ==========
    console.log('📍 步骤6：上传图标（提前操作，避免后续遮挡）...');
    let iconUploaded = false;
    globalAppreciationFail = false; // 赞赏图上传是否失败（步骤23/24设置）
    try {
      // 找到第4个 file input（图标：accept=image/png，索引3）
      const fileInputs = await page.$$('input[type="file"]');
      if (fileInputs.length >= 4) {
        await fileInputs[3].uploadFile(iconPath);
        console.log('  ✅ 图标已上传（提前）');
        iconUploaded = true;
        await sleep(3000);
      }
    } catch (e) {
      console.log('  ⚠️ 图标提前上传失败，稍后重试');
    }

    // ========== 步骤7：上传表情图片 ==========
    console.log('📍 步骤7：上传表情图片...');
    const filePaths = imageFiles.map(f => path.join(imageDir, f));
    let uploaded = false;

    // 尝试1：label[style*="opacity: 0"]
    const uploadLabel = await page.$('label[style*="opacity: 0"]');
    if (uploadLabel && !uploaded) {
      try {
        const [fileChooser] = await Promise.all([
          page.waitForFileChooser({ timeout: 8000 }),
          uploadLabel.click(),
        ]);
        await fileChooser.accept(filePaths);
        console.log(`  ✅ 已上传 ${imageFiles.length} 张图片 (方式1: label click)`);
        uploaded = true;
      } catch (e) {
        console.log(`  ⚠️ 方式1失败: ${e.message}`);
      }
    }

    // 尝试2：直接找 sticker 区的 file input（排除 icon/横幅/封面/赞赏的 input）
    if (!uploaded) {
      try {
        const allFileInputs = await page.$$('input[type="file"]');
        console.log(`  🔍 找到 ${allFileInputs.length} 个 file input`);
        // sticker 上传 input 通常是第1个（索引0），accept 为 image/png 或 image/gif
        // icon 是索引3 (accept=image/png)，横幅/封面/赞赏在后面
        let stickerInput = null;
        for (let idx = 0; idx < allFileInputs.length; idx++) {
          const accept = await allFileInputs[idx].evaluate(el => el.getAttribute('accept') || '');
          console.log(`    input[${idx}]: accept="${accept}"`);
          if (accept.includes('image') && !stickerInput) {
            stickerInput = allFileInputs[idx];
          }
        }
        if (stickerInput) {
          const [fileChooser] = await Promise.all([
            page.waitForFileChooser({ timeout: 8000 }),
            stickerInput.evaluate(el => el.click()),
          ]);
          await fileChooser.accept(filePaths);
          console.log(`  ✅ 已上传 ${imageFiles.length} 张图片 (方式2: direct input click)`);
          uploaded = true;
        }
      } catch (e) {
        console.log(`  ⚠️ 方式2失败: ${e.message}`);
      }
    }

    // 尝试3：evaluate 直接 dispatch click
    if (!uploaded) {
      try {
        const [fileChooser] = await Promise.all([
          page.waitForFileChooser({ timeout: 8000 }),
          page.evaluate(() => {
            const labels = document.querySelectorAll('label');
            for (const l of labels) {
              if (l.style.opacity === '0' || l.style.opacity === '0.0') {
                l.click();
                return true;
              }
            }
            // fallback: click any label with width 100% height 100%
            for (const l of labels) {
              if (l.style.width === '100%' && l.style.height === '100%') {
                l.click();
                return true;
              }
            }
            return false;
          }),
        ]);
        await fileChooser.accept(filePaths);
        console.log(`  ✅ 已上传 ${imageFiles.length} 张图片 (方式3: evaluate click)`);
        uploaded = true;
      } catch (e) {
        console.log(`  ⚠️ 方式3失败: ${e.message}`);
      }
    }

    if (!uploaded) {
      console.log('  ❌ 所有上传方式均失败，终止');
      throw new Error('无法触发文件上传');
    }

    // 等待图片上传完成（根据图片数量动态调整）
    const waitTime = Math.max(10000, imageFiles.length * 2000);
    console.log(`  ⏳ 等待图片上传完成（约${waitTime/1000}秒）...`);
    await sleep(waitTime);

    // ========== 步骤8：填写含义词 ==========
    console.log('📍 步骤8：填写含义词...');
    // 重新获取含义词输入框（上传后才会出现）
    const meaningInputs = await page.$$('input[placeholder="输入含义词"]');
    console.log(`  📝 找到 ${meaningInputs.length} 个含义词输入框`);
    if (meaningInputs.length === 0) {
      console.log('  ❌ 未找到含义词输入框！提交必将失败，终止');
      throw new Error('含义词输入框未找到（页面结构可能已变化）');
    }
    let meaningFilled = 0;
    for (let i = 0; i < Math.min(meaningInputs.length, meanings.length); i++) {
      // 用 nativeInputValueSetter 设值（兼容 React/Vue 框架，比 el.value= 更可靠）
      // 同时 dispatch input + change 事件
      await meaningInputs[i].evaluate((el, val) => {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, meanings[i]);
      meaningFilled++;
    }
    console.log(`  ✅ 已填写 ${meaningFilled} 个含义词`);

    // 验证含义词是否真的填进去了（防假阳性）
    const verifyMeanings = await page.evaluate(() => {
      const inputs = document.querySelectorAll('input[placeholder="输入含义词"]');
      return Array.from(inputs).map(el => el.value);
    });
    const emptyCount = verifyMeanings.filter(v => !v || v.trim() === '').length;
    if (emptyCount > 0) {
      console.log(`  ❌ 验证失败：${emptyCount} 个含义词为空！已填值示例: ${JSON.stringify(verifyMeanings.slice(0, 3))}`);
      // 兜底：对空的用 type() 重试（puppeteer 原生键盘模拟）
      console.log('  🔧 尝试用 type() 兜底重填...');
      const retryInputs = await page.$$('input[placeholder="输入含义词"]');
      for (let i = 0; i < Math.min(retryInputs.length, meanings.length); i++) {
        const currentVal = await retryInputs[i].evaluate(el => el.value);
        if (!currentVal || currentVal.trim() === '') {
          await retryInputs[i].click({ clickCount: 3 });
          await retryInputs[i].type(meanings[i]);
          await sleep(100);
        }
      }
    } else {
      console.log(`  ✅ 验证通过：16 个含义词均已正确填入`);
    }

    await sleep(1000);

    // ========== 步骤9：填写表情专辑名称 ==========
    console.log('📍 步骤9：填写名称...');
    const allInputs = await page.$$('input.weui-desktop-form__input');
    for (const input of allInputs) {
      const placeholder = await page.evaluate(el => el.placeholder, input);
      if (placeholder && placeholder.includes('填写表情专辑名称')) {
        await input.click({ clickCount: 3 }); // 清空
        await input.type(name);
        console.log(`  ✅ 名称已填写: ${name}`);
        break;
      }
    }

    // ========== 步骤10：填写介绍 ==========
    console.log('📍 步骤10：填写介绍...');
    const textareas = await page.$$('textarea.weui-desktop-form__textarea');
    for (const textarea of textareas) {
      const placeholder = await page.evaluate(el => el.placeholder, textarea);
      if (placeholder && placeholder.includes('描述表情的特点和故事')) {
        await page.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, textarea, stickerDescription);
        console.log('  ✅ 介绍已填写: ' + stickerDescription);
        break;
      }
    }

    // ========== 步骤11：填写版权信息 ==========
    console.log('📍 步骤11：填写版权信息...');
    for (const input of allInputs) {
      const placeholder = await page.evaluate(el => el.placeholder, input);
      if (placeholder && placeholder.includes('填写版权信息')) {
        await input.click({ clickCount: 3 });
        await input.type(FIXED_CONFIG.copyright);
        console.log(`  ✅ 版权已填写: ${FIXED_CONFIG.copyright}`);
        break;
      }
    }

    // ========== 步骤12：上传横幅 ==========
    console.log('📍 步骤12：上传横幅...');
    let fileInputsForAssets = await page.$$('input[type="file"]');
    if (fileInputsForAssets.length > 1) {
      await fileInputsForAssets[1].uploadFile(bannerPath);
      console.log('  ✅ 横幅已上传');
      await sleep(2000);
    }

    // ========== 步骤13：上传封面 ==========
    console.log('📍 步骤13：上传封面...');
    fileInputsForAssets = await page.$$('input[type="file"]');
    if (fileInputsForAssets.length > 2) {
      await fileInputsForAssets[2].uploadFile(coverPath);
      console.log('  ✅ 封面已上传');
      await sleep(2000);
    }

    // ========== 步骤14：上传图标（备选，如果步骤6失败） ==========
    if (!iconUploaded) {
      console.log('📍 步骤14：上传图标（备选）...');
      try {
        const allBtns = await page.$$('button.weui-desktop-btn_default');
        if (allBtns.length >= 3) {
          const [fc] = await Promise.all([
            page.waitForFileChooser({ timeout: 10000 }),
            allBtns[2].click(),
          ]);
          await fc.accept([iconPath]);
          console.log('  ✅ 图标已上传（备选）');
          await sleep(2000);
        }
      } catch (e) {
        console.log('  ⚠️ 图标上传仍失败，继续执行...');
      }
    } else {
      console.log('📍 步骤14：跳过（已在步骤6上传）');
    }

    // ========== 步骤15：类型细分 - 卡通表情/其他 ==========
    console.log('📍 步骤15：选择类型细分 - 卡通表情/其他...');
    const typeRadios = await page.$$('input[type="radio"][value="1"]');
    if (typeRadios.length > 0) {
      await page.evaluate(el => el.click(), typeRadios[0]);
      console.log('  ✅ 已选择"卡通表情/其他"');
    }

    await sleep(500);

    // ========== 步骤16：角色/内容 - 根据角色卡选择 ==========
    const roleTarget = charCard.roleTarget || (charCard.hasLaoyu ? '人物合辑' : '女人');
    console.log(`📍 步骤16：选择角色/内容 - ${roleTarget}...`);
    const dtElements = await page.$$('dt.weui-desktop-form__dropdowncascade__dt');
    for (const dt of dtElements) {
      const text = await page.evaluate(el => el.textContent, dt);
      if (text.includes('未选择') || text.includes('角色')) {
        await dt.click();
        await sleep(1000);

        // 第1步：点击 first-level "人物角色"展开二级菜单
        const firstLevelItems = await page.$$('.weui-desktop-dropdown__list-ele.first-level');
        for (const item of firstLevelItems) {
          const itemText = await item.evaluate(el => el.textContent.trim());
          if (itemText === '人物角色') {
            await item.click();
            await sleep(1500);
            break;
          }
        }

        // 第2步：在二级菜单中选择
        const subItems = await page.$$('[title*="' + roleTarget + '"]');
        if (subItems.length > 0) {
          await subItems[0].click();
          console.log(`  ✅ 已选择"${roleTarget}"`);
        }
        break;
      }
    }

    await sleep(500);

    // ========== 步骤17：表情风格 - 软萌可爱 + 日常 ==========
    console.log('📍 步骤17：选择表情风格...');
    const checkboxes = await page.$$('input[type="checkbox"]');
    for (const cb of checkboxes) {
      const val = await page.evaluate(el => el.value, cb);
      if (FIXED_CONFIG.styles.includes(val)) {
        await page.evaluate(el => el.click(), cb);
        console.log(`  ✅ 已勾选风格: ${val}`);
      }
    }

    await sleep(500);

    // ========== 步骤18：表情主题 - 万能通用 ==========
    console.log('📍 步骤18：选择表情主题 - 万能通用...');
    const themeRadios = await page.$$('input[type="radio"][value="万能通用"]');
    if (themeRadios.length > 0) {
      await page.evaluate(el => el.click(), themeRadios[0]);
      console.log('  ✅ 已选择"万能通用"');
    }

    await sleep(500);

    // ========== 步骤19：下载地区 - 全球 ==========
    console.log('📍 步骤19：选择下载地区 - 全球...');
    const regionRadios = await page.$$('input[type="radio"][value="DEF"]');
    if (regionRadios.length > 0) {
      await page.evaluate(el => el.click(), regionRadios[0]);
      console.log('  ✅ 已选择"全球"');
    }

    await sleep(500);

    // ========== 步骤20：表情价格 - 免费 ==========
    console.log('📍 步骤20：选择表情价格 - 免费...');
    const priceRadios = await page.$$('input[type="radio"][value="true"]');
    for (const radio of priceRadios) {
      const labelText = await page.evaluate(el => {
        const parent = el.closest('label');
        return parent ? parent.textContent.trim() : '';
      }, radio);
      if (labelText.includes('免费')) {
        await page.evaluate(el => el.click(), radio);
        console.log('  ✅ 已选择"免费"');
        break;
      }
    }

    await sleep(500);

    // ========== 步骤21：接受赞赏 ==========
    console.log('📍 步骤21：打开接受赞赏...');
    const allLabels = await page.$$('label.weui-desktop-form__check-label');
    for (const label of allLabels) {
      const text = await page.evaluate(el => el.textContent, label);
      if (text.includes('接受赞赏')) {
        const cb = await label.$('input[type="checkbox"]');
        if (cb) {
          const checked = await page.evaluate(el => el.checked, cb);
          if (!checked) {
            await label.click();
            console.log('  ✅ 已打开"接受赞赏"');
          } else {
            console.log('  ✅ "接受赞赏"已开启');
          }
        }
        break;
      }
    }

    // ========== 步骤22：赞赏引导语 ==========
    console.log('📍 步骤22：填写赞赏引导语...');
    const tipInputs = await page.$$('input.weui-desktop-form__input');
    for (const input of tipInputs) {
      const placeholder = await page.evaluate(el => el.placeholder, input);
      if (placeholder && placeholder.includes('最少填写5个字')) {
        await input.click({ clickCount: 3 });
        await input.type(FIXED_CONFIG.appreciationText);
        console.log(`  ✅ 赞赏引导语: ${FIXED_CONFIG.appreciationText}`);
        break;
      }
    }

    // ========== 步骤23：上传赞赏引导图 ==========
    console.log('📍 步骤23：上传赞赏引导图...');
    const guideImgPath = charCard.onlyLaoyu
      ? 'E:\\星星布丁\\微信表情包\\赞赏页\\捞鱼-赞赏引导图.png'
      : FIXED_CONFIG.appreciationGuideImg;
    let guideUploaded = false;

    // 通用赞赏图上传：通过文字标签定位对应 file input，再 uploadFile（比 fileChooser 可靠）
    const uploadAppreciation = async (labelKeywords, imgPath, name) => {
      // 方案A：按文字标签定位——找包含关键词的容器，再向上找含 file input 的祖先
      const fileInputs = await page.$$('input[type="file"]');
      console.log(`  🔍 当前共 ${fileInputs.length} 个 file input，按标签"${labelKeywords}"定位`);
      try {
        // 逐个 input 向上找祖先文字，匹配关键词
        for (let i = 0; i < fileInputs.length; i++) {
          const matched = await page.evaluate((idx, kws) => {
            let el = document.querySelectorAll('input[type="file"]')[idx];
            let p = el;
            for (let k = 0; k < 8 && p; k++) {
              const t = (p.innerText || p.textContent || '').trim();
              if (t && t.length < 120 && kws.some(w => t.includes(w))) {
                return { found: true, sample: t.slice(0, 50) };
              }
              p = p.parentElement;
            }
            return { found: false };
          }, i, labelKeywords);
          if (matched.found) {
            console.log(`  🎯 匹配到 input[${i}] (祖先含"${matched.sample}")`);
            await fileInputs[i].uploadFile(imgPath);
            await sleep(1500);
            // 处理平台裁剪弹窗：上传后若弹出"裁剪...确定"框，需点"确定"才真正生效
            try {
              const cropConfirmed = await page.evaluate(() => {
                // 找裁剪框里的"确定"按钮
                const btns = Array.from(document.querySelectorAll('button, a.weui-desktop-btn'));
                const ok = btns.find(b => {
                  const t = (b.textContent || '').trim();
                  // 排除"取消"，必须是裁剪框内的"确定"
                  return t === '确定' && b.offsetParent !== null;
                });
                if (ok) { ok.click(); return true; }
                return false;
              });
              if (cropConfirmed) {
                console.log(`  ✂️ 检测到裁剪框，已点击"确定"`);
                await sleep(1500);
              }
            } catch (e) { /* 无裁剪框，忽略 */ }
            return true;
          }
        }
      } catch (e) {
        console.log(`  ⚠️ 标签定位上传失败: ${e.message}`);
      }
      return false;
    };

    // 上传前记录赞赏区已上传的缩略图数量（用于后续验证）
    const countAppreciationThumbs = async () => {
      return await page.evaluate(() => {
        // 赞赏上传成功后会插入 img / 带 src 的元素
        const imgs = document.querySelectorAll('img[src*="blob:"], img[src*="data:"], .uploader__thumb, [class*="uploader"] img');
        return imgs.length;
      }).catch(() => 0);
    };
    const thumbsBeforeGuide = await countAppreciationThumbs();
    console.log(`  📸 赞赏区缩略图(上传前): ${thumbsBeforeGuide}`);

    guideUploaded = await uploadAppreciation(['赞赏引导图', '引导图'], guideImgPath, '赞赏引导图');
    if (guideUploaded) {
      await sleep(2500);
      // 验证：缩略图数量应增加
      const after = await countAppreciationThumbs();
      if (after > thumbsBeforeGuide) {
        console.log(`  ✅ 赞赏引导图已上传并验证 (缩略图 ${thumbsBeforeGuide}→${after}): ${path.basename(guideImgPath)}`);
      } else {
        console.log(`  ⚠️ 赞赏引导图 uploadFile 完成，但缩略图未增加 (${thumbsBeforeGuide}→${after})，可能未生效`);
        guideUploaded = false;
      }
    } else {
      console.log(`  ⚠️ 赞赏引导图未成功上传`);
    }
    // 回退：fileChooser + uploader__init 点击（保留原兜底）
    if (!guideUploaded) {
      const uploaderInits2 = await page.$$('div.uploader__init');
      console.log(`  🔄 回退 fileChooser，uploader__init 共 ${uploaderInits2.length} 个`);
      if (uploaderInits2.length >= 2) {
        try {
          const [fc] = await Promise.all([
            page.waitForFileChooser({ timeout: 8000 }),
            uploaderInits2[uploaderInits2.length - 2].click(),
          ]);
          await fc.accept([guideImgPath]);
          await sleep(2500);
          const after = await countAppreciationThumbs();
          if (after > thumbsBeforeGuide) {
            console.log(`  ✅ 赞赏引导图已上传(回退+验证): ${path.basename(guideImgPath)}`);
            guideUploaded = true;
          } else {
            console.log(`  ⚠️ 赞赏引导图回退上传未验证成功`);
          }
        } catch (e) {
          console.log(`  ⚠️ 赞赏引导图回退上传失败: ${e.message}`);
        }
      }
    }
    if (!guideUploaded) globalAppreciationFail = true;

    // ========== 步骤24：上传赞赏致谢图 ==========
    console.log('📍 步骤24：上传赞赏致谢图...');
    const thanksImgPath = charCard.onlyLaoyu
      ? 'E:\\星星布丁\\微信表情包\\赞赏页\\捞鱼-赞赏致谢图.png'
      : FIXED_CONFIG.appreciationThanksImg;
    let thanksUploaded = false;
    const thumbsBeforeThanks = await countAppreciationThumbs();
    thanksUploaded = await uploadAppreciation(['赞赏致谢图', '致谢图'], thanksImgPath, '赞赏致谢图');
    if (thanksUploaded) {
      await sleep(2500);
      const after = await countAppreciationThumbs();
      if (after > thumbsBeforeThanks) {
        console.log(`  ✅ 赞赏致谢图已上传并验证 (缩略图 ${thumbsBeforeThanks}→${after}): ${path.basename(thanksImgPath)}`);
      } else {
        console.log(`  ⚠️ 赞赏致谢图 uploadFile 完成，但缩略图未增加 (${thumbsBeforeThanks}→${after})`);
        thanksUploaded = false;
      }
    } else {
      console.log(`  ⚠️ 赞赏致谢图未成功上传`);
    }
    if (!thanksUploaded) {
      const uploaderInits3 = await page.$$('div.uploader__init');
      if (uploaderInits3.length >= 1) {
        try {
          const [fc] = await Promise.all([
            page.waitForFileChooser({ timeout: 8000 }),
            uploaderInits3[uploaderInits3.length - 1].click(),
          ]);
          await fc.accept([thanksImgPath]);
          await sleep(2500);
          const after = await countAppreciationThumbs();
          if (after > thumbsBeforeThanks) {
            console.log(`  ✅ 赞赏致谢图已上传(回退+验证): ${path.basename(thanksImgPath)}`);
            thanksUploaded = true;
          }
        } catch (e) {
          console.log(`  ⚠️ 赞赏致谢图回退上传失败: ${e.message}`);
        }
      }
    }
    if (!thanksUploaded) globalAppreciationFail = true;

    // ========== 步骤25：提交 ==========
    console.log('📍 步骤25：点击提交...');
    // 找到最后一个"提交"按钮
    const submitBtns = await page.$$('button.weui-desktop-btn_primary');
    let finalSubmitClicked = false;
    for (const btn of submitBtns) {
      const text = await page.evaluate(el => el.textContent.trim(), btn);
      if (text === '提交') {
        console.log('  ⚠️ 所有信息已填写完毕！');
        console.log('  确认无误后，将自动点击"提交"按钮...');
        await sleep(5000);
        await btn.click();
        console.log('  ✅ 已点击提交！');
        finalSubmitClicked = true;
        break;
      }
    }
    if (!finalSubmitClicked) {
      console.log('  ❌ 未找到提交按钮！');
    }

    // 等待提交结果，并检测是否成功（防假阳性）
    console.log('  ⏳ 等待提交结果（最多30秒）...');
    let submitResult = 'unknown';
    let errorMsg = '';
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      await sleep(2000);
      const pageState = await page.evaluate(() => {
        const body = document.body.innerText || '';
        // 提交成功的标志：跳转到管理页/出现成功提示
        const success = body.includes('提交成功') || body.includes('审核中')
                        || body.includes('我的表情') || body.includes('作品管理');
        // ⚠️ 失败检测：只看真正的 toast/错误弹窗，不看整页文本
        // （整页文本里有大量常驻提示如"上传文件""JPG格式"等，会误报）
        const toastEls = document.querySelectorAll(
          '.weui-desktop-toast, .weui-desktop-toast__content, ' +
          '[class*="toast-error"], [class*="toast__content"], ' +
          '.weui-desktop-alert, [role="alert"]'
        );
        const toastTexts = [];
        toastEls.forEach(el => {
          const t = el.innerText.trim();
          // 只收有实质内容的、且不是页面常驻提示的
          if (t && t.length > 2 && t.length < 200) toastTexts.push(t);
        });
        const toastText = toastTexts.join(' | ');
        // toast 必须包含明确的失败/错误动词才算失败（防止常驻提示误报）
        const failVerbs = ['失败', '错误', '不能为空', '请填写', '请上传',
                           '请重新', '格式不对', '请完善', '已存在', '重复'];
        const isRealFail = toastText && failVerbs.some(v => toastText.includes(v));
        return {
          success,
          fail: isRealFail,
          toastText,
          url: location.href,
          bodySnippet: body.slice(0, 800)
        };
      }).catch(() => ({ success: false, fail: false, toastText: '', url: '', bodySnippet: '' }));

      if (pageState.success) {
        submitResult = 'OK';
        console.log('  ✅ 提交成功！页面已跳转到管理页/出现成功提示');
        break;
      }
      if (pageState.fail) {
        submitResult = 'FAIL';
        errorMsg = pageState.toastText || '页面检测到错误提示';
        console.log(`  ❌ 提交失败：${errorMsg}`);
        console.log(`  📄 页面URL: ${pageState.url}`);
        // 保存截图供排查
        try {
          const shotPath = dir + '/_publish_fail.png';
          await page.screenshot({ path: shotPath, fullPage: true });
          console.log(`  📸 失败截图已保存: ${shotPath}`);
        } catch (_) {}
        break;
      }
      if (pageState.success) {
        submitResult = 'OK';
        console.log('  ✅ 提交成功！页面已跳转到管理页/出现成功提示');
        break;
      }
    }
    if (submitResult === 'unknown') {
      // 超时未检测到明确成功或失败，抓页面快照供排查
      console.log('  ⚠️ 30秒内未检测到明确的成功/失败信号');
      const finalBody = await page.evaluate(() => document.body.innerText.slice(0, 300)).catch(() => '');
      console.log(`  📄 页面内容片段: ${finalBody}`);
      submitResult = 'UNKNOWN';
      errorMsg = '超时未确认结果，需人工检查';
    }

    // 赞赏图上传失败：即使提交跳转成功也判为 FAIL（避免假阳性，赞赏图缺失会被平台打回）
    if (submitResult === 'OK' && globalAppreciationFail) {
      submitResult = 'FAIL';
      errorMsg = '赞赏引导图/致谢图未成功上传（缩略图验证未通过）';
      console.log(`  ❌ ${errorMsg}，本次发布判为失败，需修正后重发`);
    }

    // 记录到生产日志
    const publishStepStatus = submitResult === 'OK' ? 'OK' : (submitResult === 'FAIL' ? 'FAIL' : 'WARN');
    const { execFileSync } = require('child_process');
    try {
      execFileSync('python', [
        '-c',
        `import sys; sys.path.insert(0, r'${__dirname.replace(/\\/g,'\\\\').replace(/'/g,"\\'")}..\\..\\..\\..\\..\\\\.openclaw\\\\skills\\\\lyzbcy-sticker-creator\\\\scripts'.replace('..\\\\..\\\\..\\\\..\\\\..\\\\.openclaw','')); from production_log import log_step; log_step(r'${dir.replace(/\\/g,'\\\\').replace(/'/g,"\\'")}', '发布', '${publishStepStatus}', 'publish.js 提交结果: ${submitResult}${errorMsg ? " - " + errorMsg : ""}', {})`
      ], { stdio: 'ignore' });
      console.log(`  📝 生产日志已记录: 发布=${publishStepStatus}`);
    } catch (logErr) {
      console.log(`  ⚠️ 生产日志记录失败（不影响发布）: ${logErr.message}`);
    }

    console.log('');
    if (submitResult === 'OK') {
      console.log('🎉 发布成功！表情包已提交审核。');
    } else if (submitResult === 'FAIL') {
      console.log(`❌ 发布失败！原因: ${errorMsg}`);
      console.log('   请检查页面信息，修正后重新运行 publish.js');
    } else {
      console.log('⚠️ 发布结果未确认，请登录平台后台人工检查。');
    }

    // 自动关闭浏览器
    await sleep(3000);
    console.log('🔒 自动关闭浏览器...');
    await browser.close();
    console.log('✅ 浏览器已关闭');

    // 非 OK 时以非0退出码结束，便于上层脚本识别失败
    if (submitResult === 'FAIL') {
      process.exitCode = 1;
    }

  } catch (error) {
    console.error('❌ 执行出错:', error.message);
    console.error(error.stack);
    // 出错时也关闭浏览器
    try { await browser.close(); console.log('🔒 浏览器已关闭'); } catch (_) {}
  }
}

// CLI 执行入口
async function main() {
  const args = process.argv.slice(2);
  const params = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace('--', '');
    params[key] = args[i + 1];
  }

  if (!params.name || !params.dir) {
    console.log('用法: node publish.js --name "周三涵做表情1" --dir "E:\\星星布丁\\微信表情包\\周三涵做表情1" --type static');
    console.log('');
    console.log('参数:');
    console.log('  --name   表情专辑名称（必填）');
    console.log('  --dir    表情图片目录路径（必填）');
    console.log('  --type   表情类型 static/dynamic（默认 static）');
    console.log('  --theme  介绍中的主题思想（默认 日常交流）');
    process.exit(1);
  }

  await publishSticker({
    name: params.name,
    dir: params.dir,
    type: params.type || 'static',
    theme_idea: params.theme || '日常交流',
  });
}

if (require.main === module) {
  main();
}

module.exports = { publishSticker };
