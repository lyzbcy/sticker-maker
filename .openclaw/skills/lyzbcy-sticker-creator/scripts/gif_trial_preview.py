from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,html,sys
r=Path(sys.argv[1])
variant=sys.argv[2] if len(sys.argv)>2 else '成品'
d=r/variant
report=json.loads((d/'核验与防抖.json').read_text(encoding='utf-8'))
items=[]
for a in report['animations']:
 tracks={}
 for k,folder in [('raw','对照原始/逐帧/'),('aligned','逐帧/')]:
  gif=d/('对照原始/' if k=='raw' else '')/a['file']
  durations=[]
  with Image.open(gif) as im:
   for j in range(im.n_frames): im.seek(j);durations.append(im.info['duration'])
  tracks[k]={'folder':variant+'/'+folder+a['meaning'],'durations':durations}
 items.append({'name':a['meaning'],'file':variant+'/'+a['file'],'frames':a['actual_source_frames'],'tracks':tracks})
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
board=Image.new('RGB',(1000,1120),'#f2eee5');draw=ImageDraw.Draw(board)
for i,a in enumerate(report['animations']):
 x=(i%4)*250;y=(i//4)*280
 im=Image.open(d/(a['meaning']+'.png')).convert('RGBA');board.paste(im,(x+5,y+5),im)
 draw.text((x+10,y+248),a['meaning']+' · '+str(a['actual_source_frames'])+'帧',font=font,fill='#40342b')
board.save(r/'16枚总览.jpg',quality=93)
cards=''.join('<article><canvas id="g'+str(i)+'" width="240" height="240"></canvas><p>'+html.escape(a['name'])+' · '+str(a['frames'])+'源帧 <a href="'+html.escape(a['file'])+'" download>下载GIF</a></p></article>' for i,a in enumerate(items))
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>星星布丁 · 手绘动态表情试制</title><style>body{margin:0;background:#eeeae1;color:#3c3028;font:16px system-ui,"Microsoft YaHei",sans-serif}header,main,nav{max-width:1080px;margin:auto;padding:18px}h1{font-size:27px;margin:0 0 8px}p{line-height:1.6}nav{position:sticky;top:0;background:#eeeae1ee;z-index:2;display:flex;gap:8px;flex-wrap:wrap}button,select{font:inherit;border:1px solid #c8bfb1;background:white;border-radius:10px;padding:8px 14px;color:inherit}main{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}article{background:#fffaf2;border-radius:18px;padding:8px;text-align:center}canvas{width:100%;aspect-ratio:1;display:block}article p{font-size:13px;margin:8px 0}a{color:#8b4e2e}body.dark{background:#28302e;color:#eee5d7}body.dark nav{background:#28302eee}body.dark article{background:#414845}body.dark button,body.dark select{background:#414845;border-color:#65716b}body.dark a{color:#f0c893}@media(max-width:700px){main{grid-template-columns:repeat(2,1fr)}h1{font-size:22px}}</style><header><h1>星星布丁 · 16枚手绘动态表情</h1><p>这一弹先看动作和稳定度。切换“原始／对齐后”时保持同一时间点，可暂停、慢放和换底色。<br>每个GIF使用实际完整源帧，未补拷贝凑数；本次为试制预览。</p></header><nav><button id="play">暂停</button><button id="reset">重播</button><select id="track"><option value="aligned">对齐后</option><option value="raw">原始</option></select><select id="speed"><option value="1">原速</option><option value=".5">半速</option><option value=".25">四分之一速</option></select><button id="bg">切换底色</button><span id="status">加载中…</span></nav><main>CARDS</main><script>const items=DATA;let playing=true,elapsed=0,previous=0,track='aligned',speed=1;const loads=[];for(let i=0;i<items.length;i++){items[i].ctx=document.getElementById('g'+i).getContext('2d');for(const t of Object.values(items[i].tracks)){t.images=t.durations.map((_,j)=>{const im=new Image;loads.push(new Promise((r,x)=>{im.onload=r;im.onerror=x}));im.src=t.folder+'/'+String(j).padStart(2,'0')+'.png';return im})}}document.getElementById('play').onclick=()=>{playing=!playing;document.getElementById('play').textContent=playing?'暂停':'播放'};document.getElementById('reset').onclick=()=>elapsed=0;document.getElementById('track').onchange=e=>track=e.target.value;document.getElementById('speed').onchange=e=>speed=Number(e.target.value);document.getElementById('bg').onclick=()=>document.body.classList.toggle('dark');function tick(now){if(previous&&playing)elapsed+=(now-previous)*speed;previous=now;for(const a of items){const t=a.tracks[track];let tm=elapsed%t.durations.reduce((a,b)=>a+b,0),k=0;while(k<t.durations.length-1&&tm>=t.durations[k])tm-=t.durations[k++];a.ctx.clearRect(0,0,240,240);a.ctx.drawImage(t.images[k],0,0)}requestAnimationFrame(tick)}Promise.all(loads).then(()=>{document.getElementById('status').textContent='16枚已就绪';requestAnimationFrame(tick)}).catch(()=>document.getElementById('status').textContent='帧文件加载失败，请保持成品目录与本页同级');</script></html>'''.replace('CARDS',cards).replace('DATA',json.dumps(items,ensure_ascii=False))
(r/'点这里看16枚动态对照.html').write_text(page,encoding='utf-8')
print(json.dumps({'items':len(items),'source_frames':sum(x['frames'] for x in items),'preview':str(r/'点这里看16枚动态对照.html')},ensure_ascii=False))
