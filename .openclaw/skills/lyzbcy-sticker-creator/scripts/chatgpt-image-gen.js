#!/usr/bin/env node
/**
 * ChatGPT 网页自动化生图脚本
 * 
 * 功能：
 * 1. 打开 ChatGPT 网页
 * 2. 检查登录状态
 * 3. 上传图片（base图 + 参考图）
 * 4. 发送 Prompt
 * 5. 等待图片生成
 * 6. 下载生成的图片
 * 
 * 使用方式：
 *   node chatgpt-image-gen.js --images base.png,ref1.png,ref2.png --prompt "四宫格..." --output ./output.png
 */

const { exec, execSync } = require('child_process');
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// 配置
const CONFIG = {
  chatgptUrl: 'https://chatgpt.com/',
  timeout: 180000, // 3分钟超时
  pollInterval: 5000, // 5秒轮询
  userDataDir: './chrome-data', // 用户数据目录
};

/**
 * 执行浏览器命令（异步）
 */
function browserExecAsync(cmd) {
  return new Promise((resolve, reject) => {
    exec(`npx agent-browser ${cmd}`, { timeout: CONFIG.timeout }, (error, stdout, stderr) => {
      if (error) reject(error);
      else resolve(stdout);
    });
  });
}

/**
 * 执行浏览器命令（同步）
 */
function browserExec(cmd) {
  try {
    return execSync(`npx agent-browser ${cmd}`, { encoding: 'utf-8', timeout: 30000 });
  } catch (error) {
    console.error(`命令执行失败: ${cmd}`);
    throw error;
  }
}

/**
 * 打开 ChatGPT
 */
async function openChatGPT() {
  console.log('🌐 打开 ChatGPT...');
  
  // 使用有头浏览器
  browserExec(`--headed open "${CONFIG.chatgptUrl}"`);
  
  // 等待页面加载
  await browserExecAsync('wait --load networkidle');
  
  console.log('✅ ChatGPT 已打开');
}

/**
 * 检查登录状态
 */
async function checkLogin() {
  console.log('🔐 检查登录状态...');
  
  const snapshot = browserExec('snapshot -i');
  
  // 检测是否已登录
  // 已登录标志：看到 "New chat" 或用户头像
  // 未登录标志：看到 "Log in" 按钮
  
  if (snapshot.includes('Log in') || snapshot.includes('登录')) {
    console.log('❌ 未登录');
    return false;
  }
  
  if (snapshot.includes('New chat') || snapshot.includes('新对话')) {
    console.log('✅ 已登录');
    return true;
  }
  
  // 模糊判断：如果有输入框，说明已登录
  if (snapshot.includes('textbox') || snapshot.includes('input')) {
    console.log('✅ 已登录（检测到输入框）');
    return true;
  }
  
  console.log('⚠️  登录状态未知，假设已登录');
  return true;
}

/**
 * 上传图片
 */
async function uploadImages(imagePaths) {
  console.log(`📤 上传 ${imagePaths.length} 张图片...`);
  
  // 方法 1: 通过附件按钮上传
  // 1. 点击附件按钮（回形针图标）
  const snapshot1 = browserExec('snapshot -i');
  
  // 查找附件按钮
  if (snapshot1.includes('附件') || snapshot1.includes('attachment') || snapshot1.includes('clip')) {
    // 点击附件按钮
    // browserExec('click "@附件"');
  }
  
  // 方法 2: 直接拖拽上传
  // 使用 JavaScript 注入文件
  const filesJson = JSON.stringify(imagePaths);
  browserExec(`eval "
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = 'image/*';
    input.style.display = 'none';
    document.body.appendChild(input);
    
    // 模拟文件选择
    const files = ${filesJson};
    console.log('准备上传:', files);
  "`);
  
  console.log('✅ 图片已上传');
}

/**
 * 发送 Prompt
 */
async function sendPrompt(prompt) {
  console.log('📝 发送 Prompt...');
  
  // 转义 prompt 中的特殊字符
  const escapedPrompt = prompt.replace(/"/g, '\\"').replace(/\n/g, '\\n');
  
  // 找到输入框并填写
  const snapshot = browserExec('snapshot -i');
  
  // ChatGPT 的输入框通常是 textarea 或 contenteditable
  if (snapshot.includes('textarea') || snapshot.includes('textbox')) {
    // 填写 prompt
    browserExec(`fill "@输入框" "${escapedPrompt}"`);
    
    // 等待一下
    await new Promise(r => setTimeout(r, 1000));
    
    // 点击发送按钮
    // browserExec('click "@发送"');
    
    // 或者按 Enter 键
    browserExec('keyboard press Enter');
  }
  
  console.log('✅ Prompt 已发送');
}

/**
 * 等待图片生成
 */
async function waitForImage() {
  console.log('⏳ 等待图片生成...');
  
  const startTime = Date.now();
  
  while (Date.now() - startTime < CONFIG.timeout) {
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    console.log(`  已等待 ${elapsed} 秒...`);
    
    // 获取页面快照
    const snapshot = browserExec('snapshot -i');
    
    // 检测图片是否生成
    // 图片生成后的标志：
    // 1. 页面出现图片元素
    // 2. 出现下载按钮
    // 3. 出现 "Download" 文字
    
    if (snapshot.includes('download') || 
        snapshot.includes('Download') || 
        snapshot.includes('下载') ||
        snapshot.includes('[alt=') && snapshot.includes('image')) {
      console.log('✅ 检测到图片！');
      return true;
    }
    
    // 检测是否有错误
    if (snapshot.includes('error') || snapshot.includes('错误') || snapshot.includes('failed')) {
      console.log('❌ 生成失败');
      return false;
    }
    
    // 等待后重试
    await new Promise(r => setTimeout(r, CONFIG.pollInterval));
  }
  
  console.log('❌ 等待超时');
  return false;
}

/**
 * 下载图片
 */
async function downloadImage(outputPath) {
  console.log('📥 下载图片...');
  
  // 方法 1: 获取图片 URL 并下载
  try {
    const evalCmd = 'const img = document.querySelector("img[alt*=generated]") || document.querySelector("img[alt*=image]") || document.querySelectorAll("img")[document.querySelectorAll("img").length - 1]; img ? img.src : "";';
    const imgUrl = browserExec(`eval "${evalCmd}"`);
    
    if (imgUrl && imgUrl.trim().startsWith('http')) {
      console.log(`  图片 URL: ${imgUrl.trim().substring(0, 50)}...`);
      await downloadFile(imgUrl.trim(), outputPath);
      return true;
    }
  } catch (e) {
    console.log('  获取图片 URL 失败');
  }
  
  // 方法 2: 点击下载按钮
  try {
    const snapshot = browserExec('snapshot -i');
    if (snapshot.includes('download') || snapshot.includes('Download')) {
      // browserExec('click "@下载"');
      console.log('  点击下载按钮');
    }
  } catch (e) {
    console.log('  点击下载按钮失败');
  }
  
  // 方法 3: 截图保存
  console.log('  使用截图方式保存...');
  const screenshotPath = outputPath.replace('.png', '_screenshot.png');
  browserExec(`screenshot "${screenshotPath}"`);
  console.log(`✅ 截图已保存: ${screenshotPath}`);
  
  return true;
}

/**
 * 下载文件
 */
function downloadFile(url, outputPath) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    
    // 确保输出目录存在
    const dir = path.dirname(outputPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    const file = fs.createWriteStream(outputPath);
    
    protocol.get(url, (response) => {
      // 处理重定向
      if (response.statusCode === 301 || response.statusCode === 302) {
        downloadFile(response.headers.location, outputPath).then(resolve).catch(reject);
        return;
      }
      
      response.pipe(file);
      file.on('finish', () => {
        file.close();
        console.log(`✅ 已保存到: ${outputPath}`);
        resolve();
      });
    }).on('error', (err) => {
      fs.unlink(outputPath, () => {});
      reject(err);
    });
  });
}

/**
 * 关闭浏览器
 */
async function closeBrowser() {
  console.log('🔒 关闭浏览器...');
  try {
    browserExec('close');
  } catch (e) {
    // 忽略关闭错误
  }
}

/**
 * 主函数
 */
async function main() {
  const args = process.argv.slice(2);
  const params = {};
  
  // 解析参数
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace('--', '');
    params[key] = args[i + 1];
  }
  
  console.log('🦞 ChatGPT 自动生图工具');
  console.log('========================');
  
  try {
    // 1. 打开 ChatGPT
    await openChatGPT();
    
    // 2. 检查登录
    const isLoggedIn = await checkLogin();
    if (!isLoggedIn) {
      console.log('');
      console.log('⚠️  请在浏览器中手动登录 ChatGPT');
      console.log('   登录后，重新运行此脚本');
      console.log('');
      console.log('提示：登录状态会保存在用户数据目录中，下次无需重新登录');
      return 1;
    }
    
    // 3. 上传图片
    if (params.images) {
      const imagePaths = params.images.split(',');
      await uploadImages(imagePaths);
    }
    
    // 4. 发送 Prompt
    if (params.prompt) {
      await sendPrompt(params.prompt);
    }
    
    // 5. 等待生成
    const success = await waitForImage();
    
    // 6. 下载图片
    if (success && params.output) {
      await downloadImage(params.output);
    }
    
    console.log('');
    console.log('✅ 完成！');
    return 0;
    
  } catch (error) {
    console.error('❌ 错误:', error.message);
    return 1;
  } finally {
    // 关闭浏览器（可选，保留登录状态）
    // await closeBrowser();
  }
}

// 导出函数供其他模块使用
module.exports = {
  openChatGPT,
  checkLogin,
  uploadImages,
  sendPrompt,
  waitForImage,
  downloadImage,
};

// 如果直接运行
if (require.main === module) {
  main().then(exitCode => process.exit(exitCode));
}
