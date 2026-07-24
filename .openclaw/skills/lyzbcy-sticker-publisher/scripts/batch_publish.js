// 单批发布驱动：依次调用 publish.js 发布指定弹次，解析输出判定成功/失败，
// 失败不中断，全部记录到 _batch_result.json（每批结束会被覆盖）。
//
// 这是 batch_all.py 的底层工具——batch_all.py 负责分批/续传/重试，
// 本脚本只管"把这批弹次一个个发完"。
//
// 用法:
//   node batch_publish.js --start 19 --end 54 [--gap 8]
//   node batch_publish.js --only "20,21,23" [--gap 8]
//
// 注意：单次运行弹数不要太多（每弹约 90-115 秒），外层若有 ~10 分钟超时
// 应控制在 5 弹以内。大批量请用 batch_all.py 自动分批。
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const SCRIPT_DIR = __dirname;
const PUBLISH_JS = path.join(SCRIPT_DIR, 'publish.js');
const ROOT = 'E:\\星星布丁\\微信表情包';
const RESULT_JSON = path.join(SCRIPT_DIR, '_batch_result.json');

function parseArgs() {
  const a = process.argv.slice(2);
  const o = { start: 19, end: 54, gap: 8, only: null };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--start') o.start = parseInt(a[++i]);
    else if (a[i] === '--end') o.end = parseInt(a[++i]);
    else if (a[i] === '--gap') o.gap = parseInt(a[++i]);
    else if (a[i] === '--only') o.only = a[++i].split(',').map(s => parseInt(s.trim()));
  }
  return o;
}

const args = parseArgs();
let eps = [];
for (let ep = args.start; ep <= args.end; ep++) eps.push(ep);
if (args.only) eps = eps.filter(e => args.only.includes(e));

console.log('='.repeat(60));
console.log(`🎬 批量发布: 弹${args.start}-${args.end}，共 ${eps.length} 弹`);
console.log(`   间隔 ${args.gap}秒/弹 | 结果写入 ${path.basename(RESULT_JSON)}`);
console.log('='.repeat(60));

const results = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  for (let idx = 0; idx < eps.length; idx++) {
    const ep = eps[idx];
    const dir = path.join(ROOT, `周三涵做表情${ep}`);
    const t0 = Date.now();
    console.log(`\n📦 [${idx + 1}/${eps.length}] 发布弹${ep} ...`);

    let status = 'UNKNOWN', errMsg = '', outTail = '';
    try {
      const out = execFileSync('node', [
        PUBLISH_JS, '--name', `周三涵做表情${ep}`, '--dir', dir, '--type', 'static'
      ], { cwd: SCRIPT_DIR, encoding: 'utf8', timeout: 600000, stdio: ['ignore', 'pipe', 'pipe'] });
      outTail = out.slice(-600);
      // 解析输出判定结果
      if (out.includes('提交成功') || out.includes('🎉 发布成功') || out.includes('审核中')) status = 'OK';
      else if (out.includes('发布失败') || out.includes('❌ 提交失败')) {
        status = 'FAIL';
        const m = out.match(/提交失败[：:]\s*([^\n]+)/);
        if (m) errMsg = m[1].trim();
      } else status = 'UNKNOWN';
    } catch (e) {
      status = 'FAIL';
      errMsg = (e.message || '').slice(0, 200);
      outTail = (e.stdout ? e.stdout.slice(-400) : '') + (e.stderr ? e.stderr.slice(-200) : '');
    }

    const cost = ((Date.now() - t0) / 1000).toFixed(1);
    results.push({ ep, status, errMsg, cost, outTail });
    fs.writeFileSync(RESULT_JSON, JSON.stringify(results, null, 2), 'utf8');

    const mark = status === 'OK' ? '✅' : (status === 'FAIL' ? '❌' : '⚠️');
    console.log(`   ${mark} 弹${ep} ${status} (${cost}s)${errMsg ? ' | ' + errMsg : ''}`);

    // 实时统计
    const okN = results.filter(r => r.status === 'OK').length;
    const failN = results.filter(r => r.status === 'FAIL').length;
    console.log(`   📊 进度: ${idx + 1}/${eps.length} | 成功${okN} 失败${failN}`);

    // 弹间间隔(最后一弹不等)
    if (idx < eps.length - 1 && args.gap > 0) {
      console.log(`   ⏳ 等待 ${args.gap}秒 ...`);
      await sleep(args.gap * 1000);
    }
  }

  // 汇总
  console.log('\n' + '='.repeat(60));
  console.log('🏁 批量发布完成');
  console.log('='.repeat(60));
  const ok = results.filter(r => r.status === 'OK').map(r => r.ep);
  const fail = results.filter(r => r.status === 'FAIL').map(r => r.ep);
  const unk = results.filter(r => r.status === 'UNKNOWN').map(r => r.ep);
  console.log(`✅ 成功(${ok.length}): ${ok.join(',') || '无'}`);
  console.log(`❌ 失败(${fail.length}): ${fail.join(',') || '无'}`);
  console.log(`⚠️ 未知(${unk.length}): ${unk.join(',') || '无'}`);
  console.log(`📄 详细结果: ${RESULT_JSON}`);
})();
