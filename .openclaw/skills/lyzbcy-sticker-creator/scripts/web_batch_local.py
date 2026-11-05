"""Local image work for web_batch.cjs; imports the current project's algorithms."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from web_head_crop import crop_head

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def run(script,*args):
    return subprocess.run([sys.executable,'-X','utf8',str(HERE/script),*map(str,args)],check=True,capture_output=True,text=True,encoding='utf-8').stdout
def board(manifest,assets=False):
    rows=manifest['albums'];w=1040*(len(rows) if not assets else 2);h=1080 if not assets else 540*len(rows)
    canvas=Image.new('RGB',(w,h),'#d5d5d5');d=ImageDraw.Draw(canvas)
    for a_i,a in enumerate(rows):
        root=Path(a['dir'])
        if not assets:
            x=a_i*1040;d.text((x+8,5),a['name'],fill='black')
            files=read(root/'成品清单.json')['files']
            for i,f in enumerate(files):
                im=Image.open(root/f['file']).convert('RGBA');px=x+(i%4)*260+10;py=35+(i//4)*260
                canvas.paste(im,(px,py),im);d.text((px,py),str(i+1),fill='black')
        else:
            y=a_i*540;d.text((8,y+5),a['name'],fill='black')
            for i,p in enumerate(['封面/封面.png','图标/图标.png','横幅/横幅.png','赞赏图/赞赏引导图.png','赞赏图/赞赏致谢图.png']):
                im=Image.open(root/p).convert('RGBA');im=ImageOps.contain(im,(390,480));canvas.paste(im,(i*410+10,y+35),im)
    target=Path(manifest['logDir'])/('assets-review.jpg' if assets else 'combined-review.jpg');canvas.save(target,quality=94)
    return str(target)
def assets(manifest,review):
    for a in manifest['albums']:
        root=Path(a['dir']);r=next(x for x in review['albums'] if x['episode']==a['episode'])
        if len(r['meanings'])!=16 or len(set(r['meanings']))!=16:raise ValueError('16 unique reviewed meanings required')
        m=read(root/'成品清单.json');stage=root/'.cache/review-rename';stage.mkdir(parents=True,exist_ok=False)
        # Only move the exact 16 files whose hashes were reviewed; no directory overwrite.
        for item in m['files']:
            src=root/item['file']
            if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Sticker changed after review')
        for item in m['files']:(root/item['file']).rename(stage/f"{item['index']:02d}.png")
        for item,label in zip(m['files'],r['meanings']):
            dest=root/'最终版'/f'{label}.png'
            if dest.exists():raise FileExistsError(dest)
            (stage/f"{item['index']:02d}.png").rename(dest);item['meaning']=label;item['file']=str(dest.relative_to(root))
        write(root/'成品清单.json',m);write(root/'meanings.json',{str(i+1):s for i,s in enumerate(r['meanings'])})
        (root/'介绍.txt').write_text(r['description'],encoding='utf-8')
        proof=read(root/'头像裁切.json');proof['source']=m['files'][0]['file'];write(root/'头像裁切.json',proof)
        recipe=read(root/'发布素材清单.json')
        for source in recipe['sources']:
            if source['path'].replace('\\','/')=='最终版/01.png':source['path']=m['files'][0]['file']
        write(root/'发布素材清单.json',recipe)
    return manifest.get('reviewBoards') or str(Path(manifest['logDir'])/'review-all.jpg')

def preliminary(manifest):
    for a in manifest['albums']:
        root=Path(a['dir']);head=crop_head(root)
        (root/'介绍.txt').write_text(a['theme'][:80],encoding='utf-8')
        run('web_publish_assets.py','--episode-dir',root,'--head-source',head,'--banner-sources',head,'--tip-source',root/read(root/'成品清单.json')['files'][0]['file'])
    panels=Image.open(board(manifest)).convert('RGB')
    assets_image=Image.open(board(manifest,True)).convert('RGB')
    combined=Image.new('RGB',(max(panels.width,assets_image.width),panels.height+assets_image.height),'#d5d5d5')
    combined.paste(panels,(0,0));combined.paste(assets_image,(0,panels.height))
    target=Path(manifest['logDir'])/'review-all.jpg';combined.save(target,quality=93);return str(target)
def archive(manifest):
    from production_log import init_record,log_step_rich
    receipts=read(Path(manifest['logDir'])/'receipts.json')
    for a in manifest['albums']:
        root=Path(a['dir']);prep=read(root/'prep_state.json');receipt=next(x for x in receipts if x['name']==a['name'])
        init_record(str(root),a['episode'],{'mode':prep['mode'],'characters':prep['characters'],'reference_mode':'ChatGPT Web free theme','audit_note':'归档时间为摘要写入时间，实际执行时间见events.jsonl','source_commit':manifest['sourceCommit']})
        for step,detail in [('生图','ChatGPT网页原创base生成'),('含义预检',f'{len(manifest["albums"])}弹分组复核，平台含义去标点'),('透明化','当前引擎去洋红，白描边'),('最终版','16张透明240PNG'),('发布素材','第一格固定80%裁剪，封面同图缩图标；本弹横幅赞赏图'),('校验','当前素材SHA复核和投稿前校验通过'),('发布','SDK真实提审并按ID回读待审核')]:
            log_step_rich(str(root),step,'OK',{'events':str(Path(manifest['logDir'])/'events.jsonl'),'receipt':receipt if step=='发布' else None},detail)
        write(root/'微信投递回执.json',receipt);write(root/'当前状态.json',{'status':'verified_pending_review','sticker_id':receipt['id'],'platform_status':receipt['status'],'submitted':True})
        for f in ['events.jsonl','timings.json','report.md']:
            src=Path(manifest['logDir'])/f
            if src.exists(): (root/f).write_bytes(src.read_bytes())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['board','preliminary','assets','archive']);p.add_argument('--manifest',required=True);p.add_argument('--review')
    a=p.parse_args();m=read(a.manifest)
    if a.command=='board':print(board(m))
    elif a.command=='preliminary':print(preliminary(m))
    elif a.command=='assets':
        value=assets(m,read(a.review));print(json.dumps(value,ensure_ascii=False) if isinstance(value,list) else value)
    else:archive(m)
