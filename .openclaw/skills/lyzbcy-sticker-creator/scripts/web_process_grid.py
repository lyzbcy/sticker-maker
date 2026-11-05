"""Split and key a downloaded ChatGPT grid; never generates or publishes."""
import argparse, hashlib, json, re
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from web_source import PROJECT_ROOT
from sticker_engine.stages.grid_cutter import cut_grid
from web_edge_finish import clean_key_edges, white_outline

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--episode-dir',required=True,type=Path)
    p.add_argument('--meanings',required=True,type=Path)
    p.add_argument('--outline-px',type=float,default=2)
    p.add_argument('--fixed-grid',action='store_true',help='Use nominal cell ownership with current engine component crops after a confirmed gutter failure')
    p.add_argument('--key',choices=['#ff00ff','#00ff00'],default='#ff00ff')
    args=p.parse_args(); root=args.episode_dir
    meanings=json.loads(args.meanings.read_text(encoding='utf-8'))
    if set(meanings)!=set(map(str,range(1,17))): raise ValueError('Exactly 16 indexed meanings required')
    labels=[meanings[str(i)] for i in range(1,17)]
    if len(set(labels))!=16 or any(not 1<=len(x)<=4 or re.search(r'[\\/:*?"<>|]',x) for x in labels): raise ValueError('Meanings must be unique safe 1-4 character names')
    grid=root/'原图/grid_4x4.png'
    if not grid.is_file(): raise FileNotFoundError(grid)
    final=root/'最终版'; final.mkdir(exist_ok=True)
    if any(final.iterdir()): raise FileExistsError('Final directory must be empty; preserve earlier results')
    paths,notes=cut_grid(grid,4,root/'.cache/panels',fixed_grid=args.fixed_grid)
    keyed=root/'原图_透明ChromaKey';keyed.mkdir(exist_ok=True)
    records=[]
    sheet=Image.new('RGB',(1040,1040),'#dedede')
    for i,src in enumerate(paths,1):
        im=clean_key_edges(Image.open(src),args.key)
        alpha=np.asarray(im)[:,:,3]; ratio=float((alpha==0).mean())
        if not .03<ratio<.97: raise ValueError(f'Panel {i}: suspicious alpha {ratio:.3f}; inspect image')
        bbox=im.getbbox()
        if bbox is None:raise ValueError(f'Panel {i} empty')
        im=im.crop(bbox);im=ImageOps.contain(im,(220,220),Image.Resampling.LANCZOS)
        out=Image.new('RGBA',(240,240));out.alpha_composite(im,((240-im.width)//2,(240-im.height)//2))
        out=white_outline(out,args.outline_px)
        out.save(keyed/f'{i:02d}.png')
        target=final/(labels[i-1]+'.png');out.save(target)
        data=target.read_bytes();sha=hashlib.sha256(data).hexdigest()
        records.append({'index':i,'meaning':labels[i-1],'file':str(target.relative_to(root)),'sha256':sha,'bytes':len(data),'transparent_ratio':float((np.asarray(out)[:,:,3]==0).mean())})
        sheet.paste(out,(((i-1)%4)*260+10,((i-1)//4)*260+10),out)
    if len({r['sha256'] for r in records})!=16:raise ValueError('Duplicate final images')
    sheet.save(root/'预览.jpg',quality=95)
    (root/'成品清单.json').write_text(json.dumps({'outline_px':args.outline_px,'edge_finish':'local foreground matte + antialiased white dilation','source_sha256':hashlib.sha256(grid.read_bytes()).hexdigest(),'notes':notes,'files':records,'visual_review_required':True,'published':False},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'count':len(records),'notes':notes,'visual_review_required':True},ensure_ascii=False))
if __name__=='__main__':main()
