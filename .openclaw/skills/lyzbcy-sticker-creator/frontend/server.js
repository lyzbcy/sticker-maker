/**
 * 表情包概率控制台 — API Server v3
 * + 策略存档 + 参考图 + AI Prompt 配方 + 零概率支持
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const PORT = 3412;
const CONFIG_PATH = path.resolve(__dirname, '..', 'config.yaml');
const KEYWORDS_PATH = path.resolve(__dirname, '..', 'keywords.json');
const STRATEGIES_DIR = path.join(__dirname, 'strategies');
const PUBLIC_DIR = path.join(__dirname, 'public');

const MIME = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
};

// ======= 文件读写 =======
function readConfig() { return yaml.load(fs.readFileSync(CONFIG_PATH, 'utf8')); }
function readKeywords() { return JSON.parse(fs.readFileSync(KEYWORDS_PATH, 'utf8')); }

function writeConfig(config) {
  const diskBases = scanDiskBases(getOutputDir(config));
  const bi = mergeBaseImages(config.base_images, diskBases);
  config.base_images = bi;
  const ccp = config.character_costume_probabilities || {};
  const mp = config.mode_probabilities;
  const scp = config.single_character_probabilities;

  // NaN/undefined 全局防护
  function safeNum(v, fallback) {
    if (v === undefined || v === null || (typeof v === 'number' && isNaN(v))) return fallback;
    return v;
  }

  let out = '# 微信表情包自动化配置\n\n';
  out += '# 项目配置\n';
  out += `project:\n  name: ${config.project.name}\n  output_dir: ${config.project.output_dir}\n\n`;
  out += '# Base 图配置\nbase_images:\n';
  for (const [char, vars] of Object.entries(bi)) {
    out += `  ${char}:\n`;
    for (const [v, p] of Object.entries(vars)) out += `    ${v}: ${p}\n`;
  }
  out += '\n# 服装概率\ncharacter_costume_probabilities:\n';
  for (const [char, vars] of Object.entries(ccp)) {
    out += `  ${char}:\n`;
    for (const [v, prob] of Object.entries(vars)) out += `    ${v}: ${safeNum(prob, 0).toFixed(2)}\n`;
  }
  out += `\n# 参考图概率\nreference_probabilities:\n`;
  const rp = config.reference_probabilities || {};
  for (const [k, v] of Object.entries(rp)) {
    const num = safeNum(v, 0);
    const clean = typeof num === 'number' ? num : (num ? 1 : 0);
    out += `  "${k}": ${clean.toFixed(2)}\n`;
  }

  out += `\ncurrent_base: ${config.current_base}\n`;
  out += `duo_bases:\n  - ${config.duo_bases[0]}\n  - ${config.duo_bases[1]}\n`;
  out += 'quad_bases:\n';
  for (const q of config.quad_bases) out += `  - ${q}\n`;
  out += '\nmode_probabilities:\n';
  out += `  single: ${safeNum(mp.single, 0.7)}\n  duo: ${safeNum(mp.duo, 0.25)}\n  quad: ${safeNum(mp.quad, 0.05)}\n`;
  out += '\nsingle_character_probabilities:\n';
  for (const [k, v] of Object.entries(scp)) out += `  ${k}: ${safeNum(v, 0)}\n`;
  out += `\nreference_library: ${config.reference_library}\n`;

  // AI 模板段：从原文截取，增加安全校验
  const orig = fs.readFileSync(CONFIG_PATH, 'utf8');
  const idx = orig.indexOf('\n# AI 模板设置');
  if (idx > 0) {
    out += orig.substring(idx);
  } else {
    console.warn('[writeConfig] WARNING: 未找到 "# AI 模板设置" 段，AI 模板配置可能丢失！');
  }

  // 写入前备份
  try {
    fs.copyFileSync(CONFIG_PATH, CONFIG_PATH + '.bak');
  } catch (e) {
    console.warn('[writeConfig] 备份失败:', e.message);
  }
  fs.writeFileSync(CONFIG_PATH, out, 'utf8');
}

function writeKeywords(data) {
  fs.writeFileSync(KEYWORDS_PATH, JSON.stringify(data, null, 2), 'utf8');
}

// ======= 同比自更新概率算法 =======
function adjustProbsProportionally(existingProbs, targetKeys) {
  const result = {};
  const currentProbs = { ...existingProbs };
  
  const targetKeysSet = new Set(targetKeys);
  const remainingKeys = Object.keys(currentProbs).filter(k => targetKeysSet.has(k));
  const newKeys = targetKeys.filter(k => currentProbs[k] === undefined);
  
  const sumRemaining = remainingKeys.reduce((sum, k) => sum + (Number(currentProbs[k]) || 0), 0);
  
  if (newKeys.length > 0) {
    const pDefault = Math.round((1.0 / targetKeys.length) * 100) / 100;
    const sumNew = newKeys.length * pDefault;
    
    if (sumNew >= 0.99) {
      const eq = Math.round((1.0 / targetKeys.length) * 100) / 100;
      targetKeys.forEach(k => { result[k] = eq; });
    } else {
      newKeys.forEach(k => { result[k] = pDefault; });
      const pool = 1.0 - sumNew;
      if (sumRemaining > 0) {
        remainingKeys.forEach(k => {
          result[k] = Math.round(((currentProbs[k] * pool) / sumRemaining) * 100) / 100;
        });
      } else {
        const eq = Math.round((pool / remainingKeys.length) * 100) / 100;
        remainingKeys.forEach(k => { result[k] = eq; });
      }
    }
  } else {
    if (sumRemaining > 0) {
      remainingKeys.forEach(k => {
        result[k] = Math.round((currentProbs[k] / sumRemaining) * 100) / 100;
      });
    } else {
      const eq = Math.round((1.0 / targetKeys.length) * 100) / 100;
      targetKeys.forEach(k => { result[k] = eq; });
    }
  }
  
  targetKeys.forEach(k => {
    if (result[k] === undefined) result[k] = 0;
  });
  
  let sum = Object.values(result).reduce((a, b) => a + b, 0);
  let diff = 1.00 - sum;
  if (Math.abs(diff) > 0.001) {
    let maxKey = null;
    let maxVal = -1;
    for (const [k, v] of Object.entries(result)) {
      if (v > maxVal) {
        maxVal = v;
        maxKey = k;
      }
    }
    if (maxKey) {
      result[maxKey] = Math.round((result[maxKey] + diff) * 100) / 100;
    }
  }
  
  return result;
}

// ======= 磁盘扫描 =======
function getOutputDir(config) { return (config.project?.output_dir || '').replace(/\//g, path.sep); }

function scanDiskBases(outputDir) {
  const r = {};
  try {
    const files = fs.readdirSync(outputDir);
    const re = /^(.+)base(\d+)\.(png|jpg|jpeg)$/i;
    for (const f of files) {
      const m = f.match(re); if (!m) continue;
      const char = m[1], v = 'base' + m[2], fp = path.join(outputDir, f).replace(/\\/g, '/');
      if (!r[char]) r[char] = {};
      r[char][v] = fp;
    }
  } catch (e) {}
  return r;
}

function mergeBaseImages(configBI, diskBI) {
  const bi = { ...configBI };
  for (const [char, vars] of Object.entries(diskBI)) {
    if (!bi[char]) bi[char] = {};
    if (typeof bi[char] === 'string') bi[char] = { base1: bi[char] };
    for (const [v, fp] of Object.entries(vars)) bi[char][v] = fp;
  }
  return bi;
}

function scanRefImages(refDir) {
  const r = {};
  try {
    const dir = refDir.replace(/\//g, path.sep);
    const files = fs.readdirSync(dir);
    for (const f of files) {
      if (/\.(png|jpg|jpeg)$/i.test(f)) {
        r[f] = path.join(refDir, f).replace(/\\/g, '/');
      }
    }
  } catch (e) {}
  return r;
}

// 扫描已用参考图
function scanUsedRefImages(refDir) {
  const usedDir = refDir.replace(/\/$/, '') + '/已使用';
  const r = {};
  try {
    const dir = usedDir.replace(/\//g, path.sep);
    const files = fs.readdirSync(dir);
    for (const f of files) {
      if (/\.(png|jpg|jpeg)$/i.test(f)) {
        r[f] = path.join(usedDir, f).replace(/\\/g, '/');
      }
    }
  } catch (e) {}
  return r;
}

// ======= 构建视图 =======
function buildView(config) {
  const bi = config.base_images || {};
  const ccp = config.character_costume_probabilities || {};
  const diskBases = scanDiskBases(getOutputDir(config));
  const refDir = config.reference_library || '';
  const refFiles = scanRefImages(refDir);
  const refProbs = config.reference_probabilities || {};

  // Costumes
  const costumes = {};
  const allChars = new Set([...Object.keys(bi), ...Object.keys(diskBases)]);
  for (const char of allChars) {
    const merged = {};
    const cBi = bi[char];
    const dBases = diskBases[char] || {};
    if (typeof cBi === 'string') merged.base1 = cBi;
    else if (cBi) Object.assign(merged, cBi);
    for (const [v, fp] of Object.entries(dBases)) merged[v] = fp;
    const vNames = Object.keys(merged);
    const charProbs = ccp[char] || {};
    const allConf = vNames.every(v => charProbs[v] !== undefined);
    const configuredInBI = new Set(Object.keys(bi[char] || {}));
    costumes[char] = {};
    if (allConf) {
      for (const v of vNames) costumes[char][v] = { path: merged[v], probability: charProbs[v] };
    } else {
      const eq = Math.round(100 / vNames.length) / 100;
      for (const v of vNames) {
        costumes[char][v] = { path: merged[v], probability: eq };
        if (!configuredInBI.has(v)) costumes[char][v].source = 'disk';
      }
      // 修正舍入
      const s = Object.values(costumes[char]).reduce((a, vd) => a + vd.probability, 0);
      costumes[char][vNames[0]].probability = Math.round((costumes[char][vNames[0]].probability + 1 - s) * 100) / 100;
    }
  }

  // References (含已用标记)
  const usedRefs = scanUsedRefImages(refDir);
  const references = {};
  const refNames = Object.keys(refFiles);
  if (refNames.length > 0 && Object.keys(refProbs).length === 0) {
    const eq = Math.round(100 / refNames.length) / 100;
    for (const f of refNames) references[f] = { path: refFiles[f], probability: eq, used: !!usedRefs[f] };
    references[refNames[0]].probability = Math.round((eq + 1 - eq * refNames.length) * 100) / 100;
  } else {
    const configured = Object.keys(refProbs);
    const unconfigured = refNames.filter(f => !configured.includes(f));
    for (const f of refNames) references[f] = { path: refFiles[f], probability: refProbs[f] || 0, used: !!usedRefs[f] };
    if (unconfigured.length > 0) {
      const eq = Math.round(100 / refNames.length) / 100;
      for (const f of refNames) references[f].probability = eq;
      references[refNames[0]].probability = Math.round((eq + 1 - eq * refNames.length) * 100) / 100;
    }
  }

  return {
    mode_probabilities: config.mode_probabilities || {},
    single_character_probabilities: config.single_character_probabilities || {},
    costumes,
    references,
  };
}

// ======= API 路由 =======
function handleAPI(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return true; }

  try {
    // GET /api/config
    if (url.pathname === '/api/config' && req.method === 'GET') {
      const config = readConfig();
      // === Task 1: 自动和同比自更新概率数据 ===
      let dirty = false;
      const diskBases = scanDiskBases(getOutputDir(config));
      const bi = mergeBaseImages(config.base_images, diskBases);
      
      if (JSON.stringify(config.base_images) !== JSON.stringify(bi)) {
        config.base_images = bi;
        dirty = true;
      }
      
      const ccp = config.character_costume_probabilities || {};
      const updatedCCP = {};
      const biChars = Object.keys(bi);
      
      for (const char of biChars) {
        const vNames = Object.keys(bi[char]);
        const origProbs = ccp[char] || {};
        const adjusted = adjustProbsProportionally(origProbs, vNames);
        updatedCCP[char] = adjusted;
        if (JSON.stringify(origProbs) !== JSON.stringify(adjusted)) {
          dirty = true;
        }
      }
      // Also detect if any deleted characters were removed
      for (const char of Object.keys(ccp)) {
        if (!bi[char]) {
          dirty = true;
        }
      }
      config.character_costume_probabilities = updatedCCP;
      
      const scp = config.single_character_probabilities || {};
      const adjustedSCP = adjustProbsProportionally(scp, biChars);
      if (JSON.stringify(scp) !== JSON.stringify(adjustedSCP)) {
        config.single_character_probabilities = adjustedSCP;
        dirty = true;
      }
      
      const refDir = config.reference_library || '';
      const refFiles = scanRefImages(refDir);
      const refNames = Object.keys(refFiles);
      const refProbs = config.reference_probabilities || {};
      const updatedRefProbs = {};
      let refDirty = false;
      for (const f of refNames) {
        if (refProbs[f] !== undefined) {
          updatedRefProbs[f] = refProbs[f];
        } else {
          updatedRefProbs[f] = 1; // 默认新发现的参考图勾选使用
          refDirty = true;
        }
      }
      for (const f of Object.keys(refProbs)) {
        if (refFiles[f] === undefined) {
          refDirty = true;
        }
      }
      if (refDirty) {
        config.reference_probabilities = updatedRefProbs;
        dirty = true;
      }
      
      if (dirty) {
        writeConfig(config);
        console.log('[auto-align] 磁盘变动已同步，已对人物/服装概率进行同比调整且写入 config.yaml');
      }
      // === end auto-align ===
      const view = buildView(config);
      const kw = readKeywords();
      res.json(200, { success: true, data: { ...view, keywords: kw } });
      return true;
    }

    // GET /api/image
    if (url.pathname === '/api/image' && req.method === 'GET') {
      const p = url.searchParams.get('path'); if (!p) { res.end400(); return true; }
      if (!fs.existsSync(p)) { res.end404(); return true; }
      const ext = path.extname(p).toLowerCase();
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'image/png', 'Cache-Control': 'max-age=3600' });
      fs.createReadStream(p).pipe(res);
      return true;
    }

    // POST /api/probabilities
    if (url.pathname === '/api/probabilities' && req.method === 'POST') {
      readBody(req, body => {
        const u = JSON.parse(body);
        const config = readConfig();

        const checks = [
          { key: 'mode_probabilities', data: u.mode_probabilities },
          { key: 'single_character_probabilities', data: u.single_character_probabilities },
        ];
        for (const c of checks) {
          if (c.data) {
            const s = Object.values(c.data).reduce((a, b) => a + b, 0);
            if (Math.abs(s - 1) > 0.015) { res.end400(`概率和=${s.toFixed(2)}，必须=1`); return; }
          }
        }
        if (u.character_costume_probabilities) {
          for (const [char, probs] of Object.entries(u.character_costume_probabilities)) {
            const s = Object.values(probs).reduce((a, b) => a + b, 0);
            if (Math.abs(s - 1) > 0.015) { res.end400(`${char}服装概率和=${s.toFixed(2)}`); return; }
          }
        }
        // 参考图不再校验概率和（改为0/1勾选标志）
        if (u.reference_probabilities) {
          const clean = {};
          for (const [k, v] of Object.entries(u.reference_probabilities)) {
            clean[k] = typeof v === 'number' && !isNaN(v) ? v : (v ? 1 : 0);
          }
          u.reference_probabilities = clean;
        }

        if (u.mode_probabilities) config.mode_probabilities = u.mode_probabilities;
        if (u.single_character_probabilities) config.single_character_probabilities = u.single_character_probabilities;
        if (u.character_costume_probabilities) config.character_costume_probabilities = u.character_costume_probabilities;
        if (u.reference_probabilities) config.reference_probabilities = u.reference_probabilities;

        writeConfig(config);
        res.json(200, { success: true, data: buildView(config) });
      });
      return true;
    }

    // POST /api/reset
    if (url.pathname === '/api/reset' && req.method === 'POST') {
      const config = readConfig();
      config.mode_probabilities = { single: 0.7, duo: 0.25, quad: 0.05 };
      config.single_character_probabilities = { '星星布丁': 0.75, '捞鱼': 0.2, '周三涵': 0.03, '周五涵': 0.02 };
      // 均分服装概率
      const ccp = {};
      const bi = mergeBaseImages(config.base_images, scanDiskBases(getOutputDir(config)));
      for (const [char, vars] of Object.entries(bi)) {
        const keys = Object.keys(vars);
        const eq = Math.round(100 / keys.length) / 100;
        ccp[char] = {}; keys.forEach(k => ccp[char][k] = eq);
        ccp[char][keys[0]] = Math.round((eq + 1 - eq * keys.length) * 100) / 100;
      }
      config.character_costume_probabilities = ccp;
      // 均分参考图
      const refs = scanRefImages(config.reference_library);
      const refNames = Object.keys(refs);
      const rp = {};
      if (refNames.length > 0) {
        const eq = Math.round(100 / refNames.length) / 100;
        refNames.forEach(f => rp[f] = eq);
        rp[refNames[0]] = Math.round((eq + 1 - eq * refNames.length) * 100) / 100;
      }
      config.reference_probabilities = rp;
      writeConfig(config);
      res.json(200, { success: true, data: buildView(config) });
      return true;
    }

    // Strategy API
    if (url.pathname.startsWith('/api/strategies')) {
      if (!fs.existsSync(STRATEGIES_DIR)) fs.mkdirSync(STRATEGIES_DIR, { recursive: true });

      // GET /api/strategies → list slots dynamically
      if (url.pathname === '/api/strategies' && req.method === 'GET') {
        const slots = [];
        try {
          const files = fs.readdirSync(STRATEGIES_DIR);
          for (const f of files) {
            if (f.endsWith('.json')) {
              const id = path.basename(f, '.json');
              try {
                const content = fs.readFileSync(path.join(STRATEGIES_DIR, f), 'utf8');
                const data = JSON.parse(content);
                slots.push({ id, ...data });
              } catch (e) {}
            }
          }
        } catch (e) {}
        // Sort by timestamp descending
        slots.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
        res.json(200, { success: true, data: slots });
        return true;
      }

      // POST /api/strategies/save?id=strat_xxx
      if (url.pathname === '/api/strategies/save' && req.method === 'POST') {
        let id = url.searchParams.get('id') || '';
        if (!id) {
          id = `strat_${Date.now()}`;
        }
        readBody(req, body => {
          try {
            const data = JSON.parse(body);
            fs.writeFileSync(path.join(STRATEGIES_DIR, `${id}.json`), JSON.stringify(data, null, 2), 'utf8');
            res.json(200, { success: true, message: `策略已保存`, id });
          } catch (e) {
            res.json(400, { success: false, error: e.message });
          }
        });
        return true;
      }

      // POST /api/strategies/load?id=strat_xxx
      if (url.pathname === '/api/strategies/load' && req.method === 'POST') {
        const id = url.searchParams.get('id');
        if (!id) { res.end400('缺少 id 参数'); return true; }
        const sf = path.join(STRATEGIES_DIR, `${id}.json`);
        if (!fs.existsSync(sf)) { res.end404(`存档 ${id} 不存在`); return true; }
        const strat = JSON.parse(fs.readFileSync(sf, 'utf8'));
        const config = readConfig();
        if (strat.mode_probabilities && Object.keys(strat.mode_probabilities).length > 0) {
          config.mode_probabilities = strat.mode_probabilities;
        }
        if (strat.single_character_probabilities && Object.keys(strat.single_character_probabilities).length > 0) {
          config.single_character_probabilities = strat.single_character_probabilities;
        }
        if (strat.character_costume_probabilities && Object.keys(strat.character_costume_probabilities).length > 0) {
          config.character_costume_probabilities = strat.character_costume_probabilities;
        }
        if (strat.reference_probabilities && Object.keys(strat.reference_probabilities).length > 0) {
          config.reference_probabilities = strat.reference_probabilities;
        }
        writeConfig(config);
        res.json(200, { success: true, data: buildView(config) });
        return true;
      }

      // POST /api/strategies/delete?id=strat_xxx
      if (url.pathname === '/api/strategies/delete' && req.method === 'POST') {
        const id = url.searchParams.get('id');
        if (!id) { res.end400('缺少 id 参数'); return true; }
        const sf = path.join(STRATEGIES_DIR, `${id}.json`);
        try { if (fs.existsSync(sf)) fs.unlinkSync(sf); } catch(e) {}
        res.json(200, { success: true, message: `存档已删除` });
        return true;
      }
    }

    // POST /api/keywords → 更新关键词配方
    if (url.pathname === '/api/keywords' && req.method === 'POST') {
      readBody(req, body => {
        writeKeywords(JSON.parse(body));
        res.json(200, { success: true, message: '配方已保存' });
      });
      return true;
    }

    // GET /api/advanced → 获取高级配置
    if (url.pathname === '/api/advanced' && req.method === 'GET') {
      const config = readConfig();
      res.json(200, {
        success: true,
        data: {
          generation: config.generation || {},
          ai_template: config.ai_template || {},
          quota: config.quota || {},
          publish: config.publish || {},
        }
      });
      return true;
    }

    // POST /api/advanced → 保存高级配置
    if (url.pathname === '/api/advanced' && req.method === 'POST') {
      readBody(req, body => {
        const u = JSON.parse(body);
        const config = readConfig();
        if (u.generation) config.generation = { ...config.generation, ...u.generation };
        if (u.ai_template) config.ai_template = { ...config.ai_template, ...u.ai_template };
        if (u.quota) config.quota = { ...config.quota, ...u.quota };
        if (u.publish) config.publish = { ...config.publish, ...u.publish };
        // 直接读取原文并写回，绕过 writeConfig 的结构化生成
        const orig = fs.readFileSync(CONFIG_PATH, 'utf8');
        const idx = orig.indexOf('\n# AI 模板设置');
        let head = orig.substring(0, idx > 0 ? idx : orig.length);
        // 替换 generation 段
        if (u.generation) {
          head = head.replace(/generation:\n(\s+.+\n)*/,
            `generation:\n  mode: ${config.generation.mode}\n  quad_count: ${config.generation.quad_count}\n  dynamic: ${config.generation.dynamic}\n  frame_duration: ${config.generation.frame_duration}\n`);
        }
        if (u.publish) {
          head = head.replace(/publish:\n(\s+.+\n)*/,
            `publish:\n  auto_publish: ${config.publish.auto_publish}\n  copyright: ${config.publish.copyright}\n  type: ${config.publish.type}\n  style: ${config.publish.style}\n  theme: ${config.publish.theme}\n  region: ${config.publish.region}\n`);
        }
        if (u.ai_template) {
          head = head.replace(/background_mode:\s*"[^"]*"/, `background_mode: "${config.ai_template.background_mode}"`);
        }
        if (u.quota && u.quota.thresholds) {
          let quotaStr = 'quota:\n  thresholds:\n';
          for (const t of config.quota.thresholds) {
            quotaStr += `    - min: ${t.min}\n      local_prob: ${t.local_prob}\n`;
          }
          head = head.replace(/quota:\n(\s+.+\n(\s+.+\n)*)*/,
            quotaStr);
        }
        // 备份 + 写回
        try { fs.copyFileSync(CONFIG_PATH, CONFIG_PATH + '.bak'); } catch (e) {}
        const tail = idx > 0 ? orig.substring(idx) : '';
        fs.writeFileSync(CONFIG_PATH, head + tail, 'utf8');
        res.json(200, { success: true, message: '高级配置已保存' });
      });
      return true;
    }

    // POST /api/ref/delete → 删除参考图
    if (url.pathname === '/api/ref/delete' && req.method === 'POST') {
      readBody(req, body => {
        const { name, path: refPath } = JSON.parse(body);
        try { if (refPath && fs.existsSync(refPath)) fs.unlinkSync(refPath); } catch (e) {}
        const config = readConfig();
        if (config.reference_probabilities?.[name] !== undefined) {
          delete config.reference_probabilities[name];
          writeConfig(config);
        }
        res.json(200, { success: true, message: '已删除' });
      });
      return true;
    }

    // POST /api/ref/mark-used → 移入已用文件夹
    if (url.pathname === '/api/ref/mark-used' && req.method === 'POST') {
      readBody(req, body => {
        const { name, path: refPath } = JSON.parse(body);
        const config = readConfig();
        const refDir = config.reference_library || '';
        const usedDir = path.join(refDir.replace(/\//g, path.sep), '已使用');
        if (!fs.existsSync(usedDir)) fs.mkdirSync(usedDir, { recursive: true });
        const srcPath = refPath?.replace(/\//g, path.sep);
        const destPath = path.join(usedDir, name);
        try {
          if (srcPath && fs.existsSync(srcPath)) {
            fs.renameSync(srcPath, destPath);
          }
        } catch (e) {
          res.json(500, { success: false, error: '移动失败: ' + e.message });
          return;
        }
        // 从参考图概率中删除
        if (config.reference_probabilities?.[name] !== undefined) {
          delete config.reference_probabilities[name];
          writeConfig(config);
        }
        res.json(200, { success: true, message: '已移入已用' });
      });
      return true;
    }

  } catch (e) {
    res.json(500, { success: false, error: e.message });
    return true;
  }
  return false;
}

// ======= 辅助 =======
function readBody(req, cb) { let b = ''; req.on('data', c => b += c); req.on('end', () => cb(b)); }

// Patch response helpers
const origCreateServer = http.createServer;
http.createServer = function (handler) {
  return origCreateServer.call(http, (req, res) => {
    res.json = (code, data) => {
      res.writeHead(code, {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
      });
      res.end(JSON.stringify(data));
    };
    res.end400 = (msg) => res.json(400, { success: false, error: msg || 'Bad Request' });
    res.end404 = (msg) => res.json(404, { success: false, error: msg || 'Not Found' });
    handler(req, res);
  });
};

// ======= 静态文件 =======
function serveStatic(req, res) {
  let fp = req.url === '/' ? '/index.html' : req.url;
  fp = path.join(PUBLIC_DIR, fp);
  if (!fp.startsWith(PUBLIC_DIR)) { res.writeHead(403); res.end(); return; }
  try {
    if (fs.existsSync(fp) && fs.statSync(fp).isFile()) {
      const ext = path.extname(fp).toLowerCase();
      res.writeHead(200, {
        'Content-Type': MIME[ext] || 'application/octet-stream',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
      });
      res.end(fs.readFileSync(fp));
    } else { res.writeHead(404); res.end(); }
  } catch (e) { res.writeHead(500); res.end(); }
}

// ======= 启动 =======
const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api/')) {
    if (!handleAPI(req, res)) { res.writeHead(404); res.end(); }
  } else {
    serveStatic(req, res);
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`\n🎨 概率控制台 v3 → http://127.0.0.1:${PORT}\n`);
});
