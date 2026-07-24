#!/usr/bin/env node
/**
 * Codex CLI 图片生成脚本
 * 
 * 使用 Codex CLI 调用 ChatGPT Plus/Pro 的 GPT Image 2 生成图片
 * 无需 API key，使用已登录的 ChatGPT 订阅
 * 
 * 使用方式：
 *   node codex-image-gen.js --prompt "像素风格表情包" --output ./output.png
 *   node codex-image-gen.js --prompt "改成水彩风格" --ref ./参考图.png --output ./output.png
 */

const { execSync, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

/**
 * 解析命令行参数
 */
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { timeout: 300 };
  
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--prompt' && args[i + 1]) opts.prompt = args[++i];
    else if (args[i] === '--output' && args[i + 1]) opts.output = args[++i];
    else if (args[i] === '--ref' && args[i + 1]) opts.ref = args[++i];
    else if (args[i] === '--timeout' && args[i + 1]) opts.timeout = parseInt(args[++i], 10);
  }
  
  if (!opts.prompt) {
    console.error('Usage: node codex-image-gen.js --prompt "描述" --output ./output.png [--ref 参考图.png]');
    process.exit(1);
  }
  
  return opts;
}

/**
 * 使用 Codex CLI 生成图片
 */
async function generateImage(opts) {
  console.log('🦞 Codex CLI 图片生成');
  console.log('='.repeat(40));
  console.log(`Prompt: ${opts.prompt.substring(0, 50)}...`);
  if (opts.ref) console.log(`参考图: ${opts.ref}`);
  console.log(`输出: ${opts.output || '自动保存'}`);
  console.log(`超时: ${opts.timeout}秒`);
  console.log('='.repeat(40));
  
  // 构建 Codex 命令
  let cmd = `codex exec --enable image_generation --sandbox read-only`;
  
  // 添加参考图
  if (opts.ref) {
    if (!fs.existsSync(opts.ref)) {
      console.error(`❌ 参考图不存在: ${opts.ref}`);
      return null;
    }
    cmd += ` -i "${path.resolve(opts.ref)}"`;
  }
  
  // 添加 prompt
  cmd += ` "${opts.prompt.replace(/"/g, '\\"')}"`;
  
  console.log('\n📤 发送请求...');
  
  try {
    // 执行命令
    const result = execSync(cmd, {
      encoding: 'utf-8',
      timeout: opts.timeout * 1000,
      maxBuffer: 50 * 1024 * 1024 // 50MB buffer
    });
    
    console.log('✅ 生成完成！');
    
    // 查找最新的生成图片
    const latestImage = findLatestGeneratedImage();
    
    if (latestImage) {
      console.log(`📁 图片位置: ${latestImage}`);
      
      // 如果指定了输出路径，复制过去
      if (opts.output) {
        const outputDir = path.dirname(opts.output);
        if (!fs.existsSync(outputDir)) {
          fs.mkdirSync(outputDir, { recursive: true });
        }
        fs.copyFileSync(latestImage, opts.output);
        console.log(`✅ 已复制到: ${opts.output}`);
        return opts.output;
      }
      
      return latestImage;
    } else {
      console.log('⚠️  未找到生成的图片');
      return null;
    }
    
  } catch (error) {
    if (error.killed) {
      console.error('❌ 生成超时');
    } else {
      console.error('❌ 生成失败:', error.message);
    }
    return null;
  }
}

/**
 * 查找最新生成的图片
 */
function findLatestGeneratedImage() {
  const generatedDir = path.join(process.env.USERPROFILE || process.env.HOME, '.codex', 'generated_images');
  
  if (!fs.existsSync(generatedDir)) {
    return null;
  }
  
  let latestImage = null;
  let latestTime = 0;
  
  // 遍历所有 session 目录
  const sessions = fs.readdirSync(generatedDir);
  
  for (const session of sessions) {
    const sessionPath = path.join(generatedDir, session);
    if (!fs.statSync(sessionPath).isDirectory()) continue;
    
    // 遍历 session 内的所有图片
    const files = fs.readdirSync(sessionPath);
    
    for (const file of files) {
      if (!file.endsWith('.png')) continue;
      
      const filePath = path.join(sessionPath, file);
      const stat = fs.statSync(filePath);
      
      if (stat.mtimeMs > latestTime) {
        latestTime = stat.mtimeMs;
        latestImage = filePath;
      }
    }
  }
  
  return latestImage;
}

/**
 * 批量生成图片
 */
async function batchGenerate(prompts, outputDir, options = {}) {
  console.log(`\n🎨 批量生成 ${prompts.length} 张图片\n`);
  
  const results = [];
  
  for (let i = 0; i < prompts.length; i++) {
    const prompt = prompts[i];
    const paddedNum = String(i + 1).padStart(3, '0');
    const outputPath = path.join(outputDir, `${paddedNum}.png`);
    
    console.log(`\n[${i + 1}/${prompts.length}] ${prompt.substring(0, 50)}...`);
    
    const result = await generateImage({
      prompt,
      output: outputPath,
      ...options
    });
    
    results.push({
      index: i,
      prompt,
      success: !!result,
      output: result
    });
    
    // 间隔 2 秒，避免频率限制
    if (i < prompts.length - 1) {
      console.log('⏳ 等待 2 秒...');
      await new Promise(r => setTimeout(r, 2000));
    }
  }
  
  // 输出结果
  const successCount = results.filter(r => r.success).length;
  console.log(`\n${'='.repeat(40)}`);
  console.log(`✅ 成功: ${successCount}/${prompts.length}`);
  console.log(`📁 输出目录: ${outputDir}`);
  
  return results;
}

// 主函数
async function main() {
  const opts = parseArgs();
  const result = await generateImage(opts);
  
  if (result) {
    console.log('\n✅ 完成！');
    process.exit(0);
  } else {
    console.log('\n❌ 失败');
    process.exit(1);
  }
}

// 导出函数
module.exports = {
  generateImage,
  batchGenerate,
  findLatestGeneratedImage
};

// 如果直接运行
if (require.main === module) {
  main();
}
