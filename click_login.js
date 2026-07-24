// 使用 Playwright 点击账号密码登录
const { chromium } = require('playwright');

(async () => {
  // 连接到现有的浏览器实例
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const contexts = browser.contexts();
  const page = contexts[0].pages()[0];
  
  // 查找并点击账号密码登录
  const accountLoginBtn = await page.locator('span.active-card').first();
  if (await accountLoginBtn.isVisible()) {
    await accountLoginBtn.click();
    console.log('Clicked 账号密码登录');
  } else {
    console.log('账号密码登录 not visible');
  }
  
  // 等待账号密码表单出现
  await page.waitForTimeout(2000);
  
  // 检查是否有账号密码输入框
  const usernameInput = await page.locator('input[type="text"], input[placeholder*="账号"], input[placeholder*="手机"]').first();
  if (await usernameInput.isVisible()) {
    console.log('Found username input');
  }
  
  await browser.close();
})();
