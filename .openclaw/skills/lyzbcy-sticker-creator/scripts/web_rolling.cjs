'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { Bridge, json, sleep } = require('../../lyzbcy-sticker-publisher/scripts/web_bridge.cjs');

const run = promisify(execFile);
const composer = 'form[data-composer-placement="home"]';
const sendButton = 'button[aria-label="发送"],button[data-testid="send-button"]';
const stopButton = '[data-testid="stop-button"],button[aria-label="停止"]';
const imageSelector = `(()=>{
  const conversationId = location.pathname.split('/').at(-1);
  const transcripts = [...document.querySelectorAll('main [data-chatgpt-conversation-selection-target]')];
  const transcript = transcripts.find(node=>node.dataset.chatgptConversationSelectionTarget===conversationId) ??
    (transcripts.length===1 && transcripts[0].dataset.chatgptConversationSelectionTarget.startsWith('local-chatgpt:') ? transcripts[0] : null);
  const turns = transcript?.querySelectorAll('[data-turn-key]') ?? document.querySelectorAll('[data-testid^="conversation-turn-"]');
  const lastTurn = [...turns].at(-1);
  if (!lastTurn) return null;
  return [...lastTurn.querySelectorAll('img')].find(img=>{
    const block = img.closest('[data-talvt-turn-state]');
    return (!block || block.dataset.talvtTurnState==='complete') && img.getClientRects().length &&
      img.alt==='已生成图像 1' && img.naturalWidth>=800 && img.naturalHeight>=800;
  });
})()`;
const conversation = /^https:\/\/chatgpt\.com\/c\/[0-9a-f-]+(?:[?#].*)?$/i;
const roles = { 星星布丁: '女人', 捞鱼: '男人', 小捞咪: '猫', 布丁咪: '猫', 小丁咪: '猫' };
const gridFor = master => master.grid ?? (master.references?.length === 2 ? 6 : 8);

function validate(config) {
  if (!Array.isArray(config.masters) || !config.masters.length ||
      ![1, 2, 3].includes(config.concurrency ?? 2) ||
      !Number.isSafeInteger(config.firstEpisode) || config.firstEpisode < 1 ||
      typeof config.output !== 'string' || !config.output.trim() ||
      (config.latestStartAt !== undefined && !Number.isSafeInteger(config.latestStartAt))) {
    throw Error('Invalid batch configuration');
  }
  let totalAlbums = 0;
  for (const master of config.masters) {
    const grid = gridFor(master);
    const supportedGrids = master.nativeAlpha === true ? [3, 4, 6, 7, 8] : [6, 7, 8];
    if (!supportedGrids.includes(grid)) throw Error('Grid is unsupported for this background mode');
    const albumSize = master.albumSize ?? 16;
    if (albumSize !== 16 && !(master.nativeAlpha === true && albumSize === 8)) {
      throw Error('Eight-sticker planning requires native alpha');
    }
    const count = Math.floor(grid ** 2 / albumSize);
    if (count === 0) throw Error('Grid is too small for the selected album size');
    totalAlbums += count;
    if (master.margin !== undefined && ![15, 18, 20, 24].includes(master.margin)) throw Error('Margin must be 15, 18, 20 or 24 percent');
    if (master.referenceMode !== undefined && !['library', 'attachment'].includes(master.referenceMode)) throw Error('Unknown reference mode');
    if (master.nativeAlpha !== undefined && typeof master.nativeAlpha !== 'boolean') throw Error('nativeAlpha must be a boolean');
    if (master.captionStyle !== undefined && master.captionStyle !== 'minimal') throw Error('Unknown caption style');
    if (master.audience !== undefined && (typeof master.audience !== 'string' || !master.audience.trim())) throw Error('Audience must be a non-empty string');
    if (!Array.isArray(master.references) || master.references.length < 1 || master.references.length > 2 ||
        new Set(master.references.map(r => r.character)).size !== master.references.length ||
        new Set(master.references.map(r => roles[r.character] === '猫')).size !== 1 ||
        !master.references.every(r => Object.hasOwn(roles, r.character) &&
          (master.referenceMode === 'library'
            ? typeof r.libraryName === 'string' && r.libraryName.trim()
            : master.referenceMode === 'attachment'
              ? typeof r.file === 'string' && path.isAbsolute(r.file) && /\.(png|jpe?g)$/i.test(r.file) && /^[a-f0-9]{64}$/i.test(r.sha256 ?? '')
              : typeof r.url === 'string' && /^https:\/\/[^\s]+$/i.test(r.url) &&
              (!r.backup || /^https:\/\/[^\s]+$/i.test(r.backup)))) ||
        !Array.isArray(master.themes) || master.themes.length !== count ||
        !master.themes.every(t => typeof t === 'string' && t.trim()) ||
        (master.localMaster !== undefined && typeof master.localMaster !== 'string') ||
        (master.prices && (!Array.isArray(master.prices) || master.prices.length !== count ||
          !master.prices.every(p => p === 0 || p === 10)))) {
      throw Error(`Each master needs 1–2 distinct characters with valid references and ${count} themes`);
    }
  }
  if (!Number.isSafeInteger(config.firstEpisode + totalAlbums - 1)) throw Error('Last episode exceeds safe range');
}

function makePrompt(master) {
  const margin = master.margin ?? 15;
  const grid = gridFor(master);
  const albumSize = master.albumSize ?? 16;
  const spare = grid ** 2 % albumSize;
  const layout = `生成正方形${grid}列${grid}行共${grid ** 2}枚。按从左到右、从上到下的顺序，每连续16枚一组。${spare ? `最后${spare}格画可独立使用的备用表情。` : ''}主题依次：`;
  const refs = master.references.map(r => r.character + ' ' + r.url + (r.backup ? '（备用直链 ' + r.backup + '）' : '')).join('；');
  const source = master.referenceMode === 'library'
    ? '使用当前对话通过资料库附加的参考图片作为实际图像输入。按附件名称识别指定角色。'
    : master.referenceMode === 'attachment'
      ? '使用本消息实际上传的角色原图作为生图输入，按附件识别角色：' + master.references.map(r => r.character + '＝' + path.basename(r.file)).join('；')
      : '请实际下载原始 PNG/JPG 并解码，把图片作为生图工具的图像输入。下载失败先重试直链，再试同一原图的备用直链；仍失败则报告失败步骤。角色参考：' + refs;
  if (master.captionStyle === 'minimal' || master.nativeAlpha) {
    const groups = master.themes.map((theme, i) => `第${albumSize*i+1}–${albumSize*(i+1)}格：${theme}`).join('；');
    const reserves = spare ? `末尾${spare}格是备用，包含在${grid*grid}格内。` : '';
    const audience = master.audience?.trim() || '微信日常聊天里爱用软萌表情的朋友';
    const cats = master.references.every(r => roles[r.character] === '猫');
    const cast = cats
      ? (master.references.length === 1 ? '每格只出现指定的一只猫。' : '每格两只指定的猫都出现，脸和毛色都可辨。')
      : (master.references.length === 1 ? '每格只出现指定主角一人。' : '每格只出现指定两人，两张脸都可辨。');
    const background = master.avoidTint ? '纯洋红只作平涂底色，人物用中性柔光，发丝、皮肤和白描边上严禁出现粉紫反光或彩色边缘。' : '';
    const surface = master.nativeAlpha
      ? `背景用真正的透明 PNG Alpha。每格四边保留至少${margin}%的完全透明空隙，画面外不加底板、底色、棋盘格或阴影。白描边完整，横向和竖向的透明空隙贯通，贴纸和道具不得跨越空隙。`
      : `白描边，每格四边留${margin}%纯洋红空带，避免人物染色。${background}`;
    const reference = master.referenceMode === undefined ? `打开原图直链，把原图作为生图参考：${refs}。打不开就报告失败。` : source + '。';
    const portrait = master.nativeAlpha
      ? '每个主题组的首格是可独立发送的正面脸部近景，双人时要并排看向画面。首格无字幕、道具或独立装饰，不裁发顶；组与组首格神情不同。'
      : '首格必须无字幕，头肩置于顶部居中75%方框；不同组首格表情须可区分。';
    return `${reference}目标人群：${audience}。聊天背景：${groups}。动作、情绪、符号由你设计，每格可独立发送，同组不重复表情和动作组合。` +
      `生成一张${grid}×${grid}贴纸网格。固定${grid}行，每行正好${grid}格，按行从左到右，组尾在行中也不换行。${reserves}${cast}保留参考角色的外观与材质。${surface}无格线、标题或编号。` +
      `默认每格无字幕，靠表情、动作和符号传意。${portrait}只有确实需要时，每组最多4格各放1–2个辅助汉字。` +
      `出图后只输出一个 JSON 对象，唯一键 meanings 是包含${grid*grid}个短词的字符串数组，按实际画面顺序逐格概括，每项1–4个汉字，每组${albumSize}格不重复。JSON和短词不画进图片。`;
  }
  const themes = master.themes.map((theme, index) => `第${index * 16 + 1}–${(index + 1) * 16}格：${theme}`).join('\n');
  const poses = master.references.length === 2
    ? [
        '一人挑眉疑惑摊手、一人认真点头',
        '一人睁眼惊讶、一人弯眼忍笑',
        '一人歪头托腮、一人从肩边指向场景一侧',
        '一人从肩边递出小物、一人眼睛亮起来并伸手接',
        '一人皱眉鼓腮、一人握拳鼓劲',
        '一人用空手招呼、一人睁眼歪头回应',
        '一人紧张地抬眉、一人笑着做安抚手势',
        '一人歪头看看同伴、一人正脸笑着点赞',
        '一人微笑轻拍同伴肩膀、一人睁眼惊讶',
        '一人正脸吐气放松、一人侧一点头笑着回应',
      ]
    : ['闭眼大笑挥手', '睁眼惊讶托脸', '侧一点头皱眉思考', '眯眼笑并在脸旁比耶', '微微歪头，在脸侧竖起拇指', '鼓腮叉腰，正脸抬眉', '在脸边做小小的加油手势', '张嘴开心地眨一只眼'];
  const offset = crypto.createHash('sha256').update(themes).digest()[0] % poses.length;
  const firstCellPoses = master.themes.map((_, index) =>
    `第${index * 16 + 1}格${poses[(offset + index) % poses.length]}`).join('；');
  return source +
    '。保留脸、发型和服装。' + (master.references.length===1?'只画一位主角，首格只有这一位角色，禁止复制同一个人或加入路人。':'每组首格只画指定两位角色。') + layout + '\n' + themes +
    '\n每组以场景为主，受众只影响口吻。每行固定' + grid + '格，组尾即使落在行中也不换行。每格四边各留至少' + margin + '%纯洋红#FF00FF，横竖切缝连续，人物、道具、文字和白描边都收在中央' + (100-2*margin) + '%。白描边连续且纯白。头发从内到边沿都保持参考图的原色，尤其保留捞鱼的黑棕发色。白描边内外禁止紫色、粉紫、绿色轮廓、反光或渐变；洋红只用于背景。宁可缩小贴纸，禁止跨格，不画网格线、标题或编号。' +
    '各组首格依次用这些轮廓可辨的头肩动作：' + firstCellPoses + '。' +
    '从参考图保留身份特征，按动作重画眼睛、嘴和手势，避免用同一张脸只换道具。手势放在脸边且不能挡脸，台词放在两肩下方，缩成50像素后应靠表情和姿势区分。' +
    (master.references.length===2?'每枚两位指定角色都同框，两张脸都要露出并可辨。侧脸可用，避免背影、遮脸或只画道具。各组首格两脸朝前且放进顶部居中75%区域，两人的眼睛、嘴型和动作有明显差别。结合本组场景表现互动，小道具可放在脸侧下方，不能挡脸。':'各组首格单人头肩放进顶部居中75%区域。') +
    '图内文案用真实聊天的自然口语，长短随表达需要，字数不限。需要时自然换行，台词用黑色或深棕实心字、外围白描边，避免反白字。洋红只作背景，不用于道具和符号。字体清晰，文字和两张脸互不遮挡。每组16格只围绕该组主题。出图后附一个JSON对象：captions为按实际画面顺序抄录的'+grid*grid+'项图内原文，保留标点和措辞；meanings为同序的投稿检索关键词，每项1–4个汉字。每连续16项内检查无重词；同一意思用贴合该格画面和原话的不同短词。这两个字段各自是字符串数组，meanings只用于投稿，不能反过来限制图内文案。';
}

async function nativeClick(bridge, expression) {
  const point = await bridge.read(`(()=>{const r=(${expression})?.getBoundingClientRect();return r&&r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()`);
  if (!point) throw Error('Library control not visible');
  for (const type of ['mousePressed','mouseReleased']) {
    await bridge.call('cdp',{method:'Input.dispatchMouseEvent',params:{type,...point,button:'left',clickCount:1}});
  }
}

async function waitVisible(bridge, expression, control, attempts = 30) {
  for (let i=0; i<attempts; i++) {
    if (await bridge.read(expression)) return;
    await sleep(400);
  }
  throw Error('Library control timed out: ' + control);
}

async function attachLibrary(bridge, references) {
  await bridge.call('cdp',{method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});
  const addButton = `document.querySelector(${JSON.stringify(composer)})?.querySelector('button[aria-label="添加文件等内容"]')`;
  const menu = "[...document.querySelectorAll('button')].find(x=>x.innerText?.startsWith('从资料库添加'))";
  const search = '#library-file-picker-search';
  for (const reference of references) {
    const marker = '移除“' + reference.libraryName;
    const attached = `[...document.querySelectorAll(${JSON.stringify(composer+' button')})].some(x=>{const a=x.getAttribute('aria-label');return a===${JSON.stringify(marker+'.png”')}||a===${JSON.stringify(marker+'.jpg”')}||a===${JSON.stringify(marker+'.jpeg”')}})`;
    if (await bridge.read(attached)) continue;
    await nativeClick(bridge, addButton);
    await waitVisible(bridge, `!!(${menu})`, 'attachment menu');
    await nativeClick(bridge, menu);
    await waitVisible(bridge, `!!document.querySelector(${JSON.stringify(search)})`, 'file picker');
    await bridge.call('fill',{selector:search,value:reference.libraryName});
    const name = JSON.stringify(reference.libraryName);
    const row = `([...document.querySelectorAll('[role=dialog] button')].find(x=>x.getAttribute('aria-label')===${name})??
      [...document.querySelectorAll('[role=dialog] span')].find(x=>x.textContent.trim()===${name}))`;
    // The library can populate exact matches several seconds after the search field settles.
    await waitVisible(bridge, `!!(${row})`, 'exact library file', 60);
    await nativeClick(bridge, row);
    const confirm = "[...document.querySelectorAll('[role=dialog] button')].find(x=>x.innerText.trim()==='添加到聊天'&&!x.disabled)";
    await waitVisible(bridge, `!!(${confirm})`, 'confirm attachment');
    await nativeClick(bridge, confirm);
    await waitVisible(bridge, attached, 'composer attachment');
  }
}

function captionLists(transcript, count) {
  const lists = [...transcript.matchAll(/(?:"(captions|meanings)"\s*:\s*)?(\[\s*"(?:[^"\\]|\\.)*"(?:\s*,\s*"(?:[^"\\]|\\.)*")*\s*\])/g)]
    .flatMap(([,kind,rawList]) => {
      try {
        const items = JSON.parse(rawList);
        return items.length === count ? [{kind,items}] : [];
      } catch { return []; }
    });
  return {
    candidates: lists.find(x => x.kind === 'captions')?.items ?? lists.find(x => !x.kind)?.items,
    meaningCandidates: lists.find(x => x.kind === 'meanings')?.items
  };
}

const captionCopyButton = "[...document.querySelectorAll('button')].findLast(button=>button.innerText?.trim()==='复制 JSON')";

async function copyCaptionCard(bridge, count) {
  await bridge.call('cdp', {method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});
  const key = '__stickerCaptionCopy_' + crypto.randomBytes(6).toString('hex');
  try {
    const installed = await bridge.eval(`(()=>{const button=${captionCopyButton};if(!button||!navigator.clipboard)return false;
      const state={text:'',restores:[]};window[${JSON.stringify(key)}]=state;
      const patch=(object,name,value)=>{const own=Object.getOwnPropertyDescriptor(object,name);
        Object.defineProperty(object,name,{configurable:true,value});
        state.restores.push(()=>own?Object.defineProperty(object,name,own):delete object[name]);};
      patch(navigator.clipboard,'writeText',async text=>{state.text=String(text)});
      patch(navigator.clipboard,'write',async items=>{for(const item of items)
        if(item.types.includes('text/plain'))state.text=await(await item.getType('text/plain')).text()});
      const exec=document.execCommand.bind(document);
      patch(document,'execCommand',(name,...args)=>{if(name!=='copy')return exec(name,...args);
        state.text=String(document.activeElement?.value||getSelection());return true});
      button.scrollIntoView({block:'center'});return true})()`);
    if (!installed) return {};
    await nativeClick(bridge, captionCopyButton);
    for (let attempt=0; attempt<8; attempt++) {
      const text = await bridge.read(`window[${JSON.stringify(key)}]?.text||''`);
      if (text) {
        const parsed = JSON.parse(text);
        const valid = list => Array.isArray(list) && list.length===count && list.every(item=>typeof item==='string');
        if (valid(parsed.meanings)) {
          return {candidates:valid(parsed.captions)?parsed.captions:undefined, meaningCandidates:parsed.meanings, source:'page-copy-control'};
        }
        return {};
      }
      await sleep(250);
    }
    return {};
  } finally {
    await bridge.eval(`(()=>{const state=window[${JSON.stringify(key)}];if(!state)return;
      for(const restore of state.restores.reverse())restore();delete window[${JSON.stringify(key)}]})()`).catch(()=>{});
    await bridge.call('cdp', {method:'Emulation.setFocusEmulationEnabled',params:{enabled:false}}).catch(()=>{});
  }
}

async function readCaptions(bridge, count, timeout, meaningsOnly = false) {
  const until = Date.now() + timeout;
  let result = {};
  let triedCopyCard = false;
  do {
    const answer = await bridge.read(`({text:document.body.innerText.split('ChatGPT 说：').at(-1).slice(-24000),
      done:document.body.innerText.slice(-1200).includes('回答已完成')})`).catch(()=>null);
    if (!answer) break;
    result = {transcript:answer.text, ...captionLists(answer.text, count)};
    if (result.meaningCandidates && (meaningsOnly || result.candidates)) break;
    if (!triedCopyCard && answer.text.includes('复制 JSON')) {
      triedCopyCard = true;
      const copied = await copyCaptionCard(bridge, count).catch(()=>({}));
      if (copied.meaningCandidates && (meaningsOnly || copied.candidates)) return {...result,...copied};
    }
    if (answer.done && result.candidates) break;
    await sleep(500);
  } while (Date.now() < until);
  return result;
}

async function readExistingCaptions(responsePath, grid) {
  if (!responsePath || ![6, 7, 8].includes(grid)) throw Error('Expected response.json and its grid size');
  const previous = JSON.parse(await fs.readFile(responsePath, 'utf8'));
  if (!conversation.test(previous.url ?? '')) throw Error('Missing original ChatGPT conversation URL');
  const bridge = new Bridge({session:'sticker-caption-readback-'+crypto.randomUUID()});
  const tab = await bridge.call('navigate', {url:previous.url, newTab:true, group_title:'表情台词回读'});
  await bridge.attach(tab.tabId);
  try {
    if (await bridge.eval('location.href') !== previous.url) throw Error('Original conversation did not open');
    const result = await readCaptions(bridge, grid ** 2, 15000);
    const updated = {...previous, ...Object.fromEntries(Object.entries(result).filter(([, value]) => value !== undefined))};
    await json(responsePath, updated);
    console.log(JSON.stringify({captions:updated.candidates?.length??0, meanings:updated.meaningCandidates?.length??0}));
  } finally {
    const {tabs} = await bridge.call('list_tabs');
    if (tabs.some(t => t.tabId===tab.tabId && !t.borrowed && t.url===previous.url)) await bridge.call('close_tab');
  }
}

async function openGenerationTab(bridge, pool) {
  const home = {url:'https://chatgpt.com/',group_title:'表情包连续制作'};
  if (!pool?.ready) return bridge.call('navigate', {...home,newTab:true});
  const {tabId, url} = pool.ready;
  const {tabs} = await bridge.call('list_tabs');
  const tab = tabs.find(entry=>entry.tabId===tabId);
  if (tab && (tab.borrowed || tab.url!==url)) throw Error('Previously owned generation tab changed');
  if (tab) await bridge.attach(tabId);
  const next = await bridge.call('navigate', {...home,newTab:!tab});
  if (tab && next.tabId!==tabId) throw Error('Generation tab reuse did not preserve tab identity');
  pool.ready = null;
  await pool.save();
  return next;
}

async function produce(master, state, save, bridge, raw, pool, shouldStop, prompt = makePrompt(master)) {
  if (master.localMaster) {
    await fs.copyFile(master.localMaster, raw);
    return;
  }
  const deadline = Date.now() + 8 * 60_000;
  if (!state.sendIntentAt) {
    state.sendStarted ??= Date.now();
    if (!state.tabId) {
      const priorTab = pool?.ready?.tabId;
      state.tabId = (await openGenerationTab(bridge,pool)).tabId;
      if (state.tabId===priorTab) state.reusedGenerationTab = true;
      await save();
    }
    await bridge.attach(state.tabId);
    while (Date.now() < deadline) {
      const ready = await bridge.read(`location.href==='https://chatgpt.com/'&&!!document.querySelector(${JSON.stringify(composer+' [contenteditable="true"]')})`);
      if (ready) break;
      await sleep(500);
    }
    if (Date.now() >= deadline) throw Error('ChatGPT composer unavailable');
    if (master.referenceMode === 'library') {
      try {
        await attachLibrary(bridge, master.references);
      } catch (error) {
        if (!/Library control/.test(String(error))) throw error;
        state.libraryRetryAt = Date.now();
        state.libraryRetryReason = String(error);
        await save();
        await bridge.call('cdp', {method:'Page.reload',params:{}});
        await waitVisible(bridge, `!!document.querySelector(${JSON.stringify(composer+' [contenteditable="true"]')})`, 'reloaded composer');
        await attachLibrary(bridge, master.references);
      }
    }
    await bridge.call('fill', { selector: composer + ' [contenteditable="true"]', value: prompt });
    await waitVisible(bridge, `!!document.querySelector(${JSON.stringify(composer)})?.querySelector(${JSON.stringify('button[aria-label="发送"]:not([disabled]),button[data-testid="send-button"]:not([disabled])')})`, 'enabled send button', 12);
    const attachmentReady = `f.querySelectorAll('[data-composer-attachments] img').length===${master.references.length}&&!f.querySelector('[role="progressbar"],[data-composer-attachments] [role="alert"]')`;
    if (master.referenceMode === 'attachment') {
      const files = master.references.map(r => r.file);
      for (const reference of master.references) {
        const actual = crypto.createHash('sha256').update(await fs.readFile(reference.file)).digest('hex');
        if (actual !== reference.sha256.toLowerCase()) throw Error('Reference file hash mismatch');
      }
      const input = composer + ' input[type=file][accept="image/*"][multiple]';
      await waitVisible(bridge, `!!document.querySelector(${JSON.stringify(input)})`, 'image upload input');
      const attachmentCount = await bridge.read(`document.querySelector(${JSON.stringify(composer)})?.querySelectorAll('[data-composer-attachments] img').length`);
      if (attachmentCount === 0) {
        state.attachmentUploadIntentAt = Date.now();
        await save();
        await bridge.call('upload', {selector:input, files});
      }
      else if (attachmentCount !== files.length || !state.attachmentUploadIntentAt) throw Error('Existing attachments need reconciliation');
      await waitVisible(bridge, `(()=>{const f=document.querySelector(${JSON.stringify(composer)});return !!f&&(${attachmentReady})&&!!f.querySelector(${JSON.stringify(sendButton)})&&!f.querySelector(${JSON.stringify(sendButton)}).disabled})()`, 'verified reference attachments', 120);
      state.attachmentCount = files.length;
    }
    if (await shouldStop?.()) {
      const paused = new Error('Generation paused before send');
      paused.code = 'GENERATION_PAUSED';
      throw paused;
    }
    state.sendIntentAt = Date.now();
    await save();
    await bridge.call('evaluate', {code: `(()=>{const f=document.querySelector(${JSON.stringify(composer)});const b=f?.querySelector(${JSON.stringify(sendButton)});if(!b||b.disabled${master.referenceMode==='attachment'?`||!(${attachmentReady})`:''})throw Error('Send unavailable');b.click();return true})()`});
    state.sentAt = Date.now();
    await save();
  }
  let interruption;
  let visibleImageSince;
  while (Date.now() < deadline) {
    try {
      try {
        await bridge.attach(state.tabId);
      } catch (error) {
        if (!conversation.test(state.url || '') || !/No tab with id/i.test(String(error))) throw error;
        state.tabId = (await bridge.call('navigate', { url: state.url, newTab: true, group_title: '表情包连续制作' })).tabId;
        await save();
      }
      const info = await bridge.read(`({url:location.href,hasImage:!!(${imageSelector}),pending:!!document.querySelector(${JSON.stringify(stopButton)})})`);
      if (conversation.test(info.url) && info.url !== state.url) {
        if (state.url) throw Error('Original conversation no longer selected');
        state.url = info.url;
        await save();
      }
      if (interruption) {
        state.reconnectMs = (state.reconnectMs || 0) + Date.now() - interruption;
        interruption = undefined;
        await save();
      }
      const requestAt = state.linkRetryIntentAt ?? state.sentAt;
      if (state.url && info.url === state.url && info.pending && !info.hasImage &&
          requestAt && !state.pendingViewReloadAt && Date.now() - requestAt >= 5 * 60_000) {
        // The background tab can keep showing a stale pending response after the server completes.
        state.pendingViewReloadAt = Date.now();
        await save();
        await bridge.call('cdp', {method:'Page.reload',params:{}});
        continue;
      }
      if (state.url && info.url === state.url && info.hasImage && info.pending) {
        visibleImageSince ??= Date.now();
        if (!master.captureCompletedImageWhilePending && !state.collectionReloadAt &&
            Date.now() - visibleImageSince >= (master.collectionReloadAfterMs ?? 45_000)) {
          state.collectionReloadAt = Date.now();
          await save();
          await bridge.call('cdp', {method:'Page.reload',params:{}});
          continue;
        }
      } else {
        visibleImageSince = undefined;
      }
      const canCaptureWhilePending = master.captureCompletedImageWhilePending && visibleImageSince &&
        Date.now() - visibleImageSince >= (master.collectionReloadAfterMs ?? 45_000);
      if (state.url && info.url === state.url && info.hasImage && (!info.pending || canCaptureWhilePending)) {
        state.imageReadyAt ??= Date.now();
        await bridge.call('cdp', {method:'Emulation.setFocusEmulationEnabled',params:{enabled:true}});
        const downloadKey = '__rollingSticker_' + crypto.randomUUID().replaceAll('-', '');
        await bridge.job(downloadKey, `if(location.href!==${JSON.stringify(state.url)})throw Error('Original conversation no longer selected');const im=${imageSelector};if(!im)throw Error('Latest turn image no longer available');const r=await fetch(im.src);if(!r.ok)throw Error('Image download '+r.status);const b=await r.blob();return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(b)})`);
        const {result} = await bridge.wait(downloadKey, {timeout:20000});
        if (!/^data:image\/[^;]+;base64,/.test(result)) throw Error('Image download returned unexpected data');
        await fs.writeFile(raw + '.partial', Buffer.from(result.split(',')[1], 'base64'));
        await fs.rename(raw + '.partial', raw);
        const captions = await readCaptions(bridge, gridFor(master)**2, 12000, master.captionStyle === 'minimal');
        await json(path.join(path.dirname(raw), 'response.json'), {url:state.url, ...captions});
        return;
      }
    } catch (error) {
      interruption ??= Date.now();
      state.lastConnectionError = String(error);
      await save();
    }
    if (state.url && !interruption) {
      const failed = await bridge.read(`(()=>{const s=document.body.innerText;const turn=s.split('你说：').at(-1);const reply=turn.split('ChatGPT 说：').at(-1);
        const transcript=[...document.querySelectorAll('[data-chatgpt-conversation-selection-target]')].find(node=>node.dataset.chatgptConversationSelectionTarget===location.pathname.split('/').at(-1));
        const lastTurn=[...(transcript?.querySelectorAll('[data-turn-key]')??[])].at(-1);
        const completed=turn.includes('回答已完成')||!!lastTurn?.querySelector('[data-talvt-turn-state="complete"]');
        return location.href===${JSON.stringify(state.url)}&&completed&&turn.includes('ChatGPT 说：')&&
          !document.querySelector('button[aria-label="停止"],button[data-testid="stop-button"]')&&
          /下载.{0,45}失败|未能成功下载|无法下载|无法.{0,30}图像参考|连接超时|原图获取失败|域名.{0,35}解析(?:错误|失败)|DNS.{0,18}解析(?:错误|失败)|HTTP 下载阶段/.test(reply)})()`).catch(()=>false);
      if (failed) {
        if (master.referenceMode !== undefined || state.linkRetryIntentAt) throw Error('Reference download failed after one retry');
        const thread = 'form[data-composer-placement="thread"]';
        await bridge.call('fill',{selector:thread+' [contenteditable="true"]',value:prompt});
        const ready = await bridge.read(`!!document.querySelector(${JSON.stringify(thread)})?.querySelector('button[aria-label="发送"]:not([disabled]),button[data-testid="send-button"]:not([disabled])')`);
        if (!ready) throw Error('Link retry composer not ready');
        state.linkRetryIntentAt = Date.now();
        await save();
        await bridge.call('evaluate',{code:`(()=>{const b=document.querySelector(${JSON.stringify(thread)})?.querySelector(${JSON.stringify(sendButton)});if(!b||b.disabled)throw Error('Retry unavailable');b.click();return true})()`});
      }
    }
    await sleep(interruption ? 4000 : 1800);
  }
  if (interruption) state.reconnectMs = (state.reconnectMs || 0) + Date.now() - interruption;
  throw Error('Original request did not return a usable image in the observation window; inspect its conversation before resending');
}

async function main(configPath, {resumeSentOnly = false, reuseGenerationTab = false, stopFile} = {}) {
  const config = JSON.parse(await fs.readFile(configPath, 'utf8'));
  validate(config);
  if (config.masters.some(master => master.referenceMode === 'attachment')) {
    await run(config.python || 'python', ['-c', 'import cv2, PIL, scipy'], {windowsHide:true});
  }
  const output = path.resolve(config.output);
  await fs.mkdir(output, {recursive:true});
  const lockPath = path.join(output, 'run.lock');
  const lock = await fs.open(lockPath, 'wx');
  let pool;
  try {
    await lock.writeFile(String(process.pid));
    await new Bridge({url:config.daemonUrl, session:'sticker-rolling-check'}).call('list_tabs');
    const digest = crypto.createHash('sha256').update(JSON.stringify(config)).digest('hex');
    const identity = path.join(output, 'config.sha256');
    const previous = await fs.readFile(identity, 'utf8').catch(error => {
      if (error.code !== 'ENOENT') throw error;
      return null;
    });
    if (previous && previous !== digest) throw Error('Output belongs to another configuration');
    if (!previous) await fs.writeFile(identity, digest);
    if (reuseGenerationTab && !resumeSentOnly) {
      const file = path.join(output,'reusable-generation-tab.json');
      const session = 'sticker-rolling-reuse-'+crypto.createHash('sha256').update(output.toLowerCase()).digest('hex').slice(0,20);
      const ready = await fs.readFile(file,'utf8').then(JSON.parse).catch(error=>{
        if (error.code!=='ENOENT') throw error;
        return null;
      });
      pool = {session,ready,save:()=>json(file,pool.ready)};
    }
    let cursor = 0;
    const results = [];
    const shouldStop = () => {
      if (resumeSentOnly) return false;
      if (config.latestStartAt !== undefined && Date.now() >= config.latestStartAt) return true;
      return stopFile ? fs.stat(stopFile).then(()=>true,error=>{
        if (error.code!=='ENOENT') throw error;
        return false;
      }) : false;
    };
    const worker = async () => {
      while (cursor < config.masters.length) {
        if (await shouldStop()) break;
        if (cursor >= config.masters.length) break;
        const index = cursor++;
        const master = config.masters[index];
        const dir = path.join(output, String(index + 1).padStart(3, '0'));
        await fs.mkdir(dir, {recursive:true});
        const statePath = path.join(dir, 'state.json');
        const state = await fs.readFile(statePath,'utf8').then(JSON.parse).catch(error => {
          if (error.code !== 'ENOENT') throw error;
          return {status:'queued',session:pool?.session??'sticker-rolling-'+crypto.randomUUID()};
        });
        if (resumeSentOnly && !state.sendIntentAt) continue;
        const save = () => json(statePath, state);
        const bridge = new Bridge({url:config.daemonUrl, session:state.session});
        const raw = path.join(dir, 'master.png');
        const exists = file => fs.stat(file).then(() => true, error => {
          if (error.code === 'ENOENT') return false;
          throw error;
        });
        try {
          if (state.status !== 'ready' && state.status !== 'review_required' && state.status !== 'reference_failed') {
            state.status = 'generating';
            await save();
            if (!await exists(raw)) await produce(master,state,save,bridge,raw,state.session===pool?.session?pool:undefined,shouldStop);
            state.downloadedAt ??= Date.now();
            const tabs = state.tabId ? await bridge.call('list_tabs').catch(() => ({tabs:[]})) : {tabs:[]};
            if (tabs.tabs.some(t => t.tabId === state.tabId && !t.borrowed && t.url === state.url)) {
              try {
                const responsePath = path.join(dir,'response.json');
                const response = pool?.session===state.session && await exists(responsePath)
                  ? JSON.parse(await fs.readFile(responsePath,'utf8')) : null;
                if (response?.url===state.url && conversation.test(state.url??'')) {
                  pool.ready = {tabId:state.tabId,url:state.url,statePath};
                  await pool.save();
                  state.tabRetainedForReuse = true;
                } else {
                  await bridge.attach(state.tabId);
                  state.tabClosed = (await bridge.call('close_tab')).closed;
                }
              } catch (error) {
                state.tabCloseError = String(error);
              }
            }
            if (state.processingStartedAt) throw Error('Previous local processing interrupted; inspect files before rerunning');
            state.processingStartedAt = Date.now();
            await save();
            if (master.nativeAlpha) {
              const alphaDir = path.join(dir, 'alpha-cells');
              const python = config.python || 'python';
              await run(python, ['-X', 'utf8', path.join(__dirname, 'web_split_alpha.py'),
                '--source', raw, '--output', alphaDir, '--grid', String(gridFor(master))], {windowsHide:true});
              state.board = path.join(alphaDir, '透明分格复核.jpg');
              state.alphaProof = path.join(alphaDir, '分格证据.json');
            } else {
              const characters = master.references.map(r => r.character);
              const albums = await Promise.all(master.themes.map(async (theme, offset) => {
                const episode = config.firstEpisode + config.masters.slice(0,index).reduce((total,item)=>total+item.themes.length,0) + offset;
                const albumDir = path.join(dir, String(episode));
                await json(path.join(albumDir,'prep_state.json'), {characters});
                return {episode, theme, dir:albumDir, name:'周三涵做表情'+episode,
                  role:characters.every(name=>roles[name]==='猫')?'猫':characters.length===2?'人物合辑':roles[characters[0]],priceBeans:master.prices?.[offset]??0};
              }));
              const manifest = path.join(dir,'manifest.json');
              await json(manifest,{albums,logDir:dir,session:state.session,platformTabId:config.platformTabId,
                startedAt:state.sendIntentAt??state.processingStartedAt,retainFinalOnly:true});
              const python = config.python || 'python';
              const call = (script, ...args) => run(python,['-X','utf8',path.join(__dirname,script),...args],{windowsHide:true});
              const grid = gridFor(master);
              const split = file => call('web_static_density.py','--master',file,'--manifest',manifest,'--cols',String(grid),'--rows',String(grid));
              try {
                await split(raw);
              } catch (error) {
                if (![6, 8].includes(grid) || !String(error.stderr).includes('requires clean zero-foreground cuts')) throw error;
                const isolated = path.join(dir, 'isolated-master.png');
                await call('web_isolate_sheet.py', '--master', raw, '--cells', String(grid), '--assign-detached', '--out', isolated);
                state.componentProof = path.join(dir, 'isolated-master.components.json');
                await save();
                await split(isolated);
              }
              if (config.ocrFallback === true) {
                const response = await fs.readFile(path.join(dir, 'response.json'), 'utf8')
                  .then(JSON.parse).catch(() => ({}));
                if (response?.candidates?.length !== grid ** 2) {
                  try {
                    await call('web_ocr_candidates.py', '--manifest', manifest, '--out', path.join(dir, 'ocr-candidates.json'), '--captions');
                  } catch (error) {
                    state.ocrError = String(error);
                  }
                }
              }
              const {stdout:boardPath} = await call('web_batch_local.py','preliminary','--manifest',manifest,...(pool?['--compact-only']:[]));
              const readyAt = Date.now();
              for (const album of albums) Object.assign(album, {
                sendStarted:state.sendStarted, sentAt:state.sentAt??state.sendIntentAt,
                imageReadyAt:state.imageReadyAt??state.downloadedAt, processMs:readyAt-state.processingStartedAt
              });
              const prepared = JSON.parse(await fs.readFile(manifest,'utf8'));
              await json(manifest,{...prepared,albums,reviewStartedAt:readyAt});
              state.board = boardPath.trim();
            }
            state.status = 'ready';
            state.readyAt = Date.now();
            delete state.error;
          }
        } catch (error) {
          const paused = error.code === 'GENERATION_PAUSED';
          state.status = paused ? 'paused_before_send' : state.processingStartedAt ? 'review_required'
            : error.message === 'Reference download failed after one retry' ? 'reference_failed' : 'needs_reconnect';
          state.error = String(error.stderr || error);
          if (state.tabId && !state.sendIntentAt && !state.url &&
              (paused || /Library control|ChatGPT composer unavailable/.test(state.error))) {
            try {
              const {tabs} = await bridge.call('list_tabs');
              const tab = tabs.find(t => t.tabId === state.tabId && !t.borrowed && t.url === 'https://chatgpt.com/');
              if (tab) {
                await bridge.attach(state.tabId);
                if ((await bridge.call('close_tab')).closed) {
                  delete state.tabId;
                  state.unsentTabClosed = true;
                }
              }
            } catch (closeError) {
              state.tabCloseError = String(closeError);
            }
          }
        }
        await save();
        const result = {master:index+1, ...state};
        results.push(result);
        console.log(JSON.stringify(result));
        if (pool && ['needs_reconnect','reference_failed'].includes(state.status)) {
          throw Error('Single generation tab paused; reconcile the original request before opening another tab');
        }
        if (state.status === 'needs_reconnect' &&
            /extension_not_connected|Failed to connect to 127\.0\.0\.1 port/.test(state.error ?? '')) {
          cursor = config.masters.length;
          throw Error('Browser bridge disconnected; resume with the same configuration after reconnecting');
        }
      }
    };
    const workers = await Promise.allSettled(Array.from({length: Math.min(config.masters.length,pool?1:(config.concurrency??2))}, worker));
    const failed = workers.find(result => result.status === 'rejected');
    if (failed) throw failed.reason;
    await json(path.join(output,'summary.json'),results.sort((a,b)=>a.master-b.master));
    if (results.some(x=>!['ready','paused_before_send'].includes(x.status))) process.exitCode=1;
  } finally {
    try {
      if (pool?.ready) {
        const {tabId,url,statePath} = pool.ready;
        const bridge = new Bridge({url:config.daemonUrl,session:pool.session});
        const {tabs} = await bridge.call('list_tabs');
        if (tabs.some(tab=>tab.tabId===tabId&&!tab.borrowed&&tab.url===url)) {
          await bridge.attach(tabId);
          if ((await bridge.call('close_tab')).closed) {
            const state = JSON.parse(await fs.readFile(statePath,'utf8'));
            await json(statePath,{...state,tabClosed:true,tabClosedAt:Date.now()});
            pool.ready = null;
            await pool.save();
          }
        }
      }
    } catch (error) {
      console.error('Owned generation tab cleanup pending: '+String(error));
    } finally {
      await lock.close();
      await fs.unlink(lockPath);
    }
  }
}

if (require.main === module) {
  const configPath = process.argv[2];
  if (!configPath || configPath === '--help') {
    console.log('Usage: node web_rolling.cjs config.json [--resume-sent-only | --reuse-generation-tab] [--stop-file FILE]\n       node web_rolling.cjs --read-captions response.json GRID');
  } else {
    const stopIndex = process.argv.indexOf('--stop-file');
    const stopFile = stopIndex === -1 ? undefined : process.argv[stopIndex+1];
    if (stopIndex !== -1 && (!stopFile || stopFile.startsWith('--'))) {
      console.error('Specify a stop-file path');
      process.exit(1);
    }
    const operation = configPath==='--read-captions'
      ? readExistingCaptions(process.argv[3], Number(process.argv[4]))
      : main(configPath, {
        resumeSentOnly:process.argv.includes('--resume-sent-only'),
        reuseGenerationTab:process.argv.includes('--reuse-generation-tab'),stopFile
      });
    operation.catch(error=>{console.error(String(error));process.exitCode=1;});
  }
}

module.exports = { produce };
