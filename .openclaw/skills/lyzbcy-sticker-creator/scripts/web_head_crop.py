"""First panel, fixed top-center 80% square. No erasing or contour masks."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image
from web_edge_finish import clean_key_edges

def center_square(image,fraction=.8):
    if not .5<=fraction<=1:raise ValueError('Invalid square fraction')
    side=round(min(image.size)*fraction);x=(image.width-side)//2;y=0
    box=(x,y,x+side,y+side);return image.crop(box),box

def crop_head(root,index=1):
    if index!=1:raise ValueError('First-panel policy: no alternative panel selection')
    root=Path(root);manifest=json.loads((root/'成品清单.json').read_text(encoding='utf-8'))
    item=next(x for x in manifest['files'] if x['index']==1)
    sticker=root/item['file'];sticker.resolve().relative_to((root/'最终版').resolve())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(sticker)!=item['sha256']:raise ValueError('First sticker changed')
    grid=root/'原图/grid_4x4.png'
    if digest(grid)!=manifest['source_sha256']:raise ValueError('Grid changed')
    original=Image.open(grid).convert('RGB')
    # Preserve generation-time margins; never tighten around the subject.
    tile=original.crop((0,0,round(original.width/4),round(original.height/4)))
    raw=root/'原图/头像第一格原始.png';tile.save(raw)
    keyed=clean_key_edges(tile,'#ff00ff') # ordinary background removal only
    crop,box=center_square(keyed,.8)
    target=root/'原图/_noword/封面头像源.png';target.parent.mkdir(parents=True,exist_ok=True)
    crop.resize((240,240),Image.Resampling.LANCZOS).save(target)
    proof={'source':item['file'],'panel_index':1,'source_sha256':digest(sticker),
           'pixel_source':str(raw.relative_to(root)),'pixel_source_sha256':digest(raw),
           'grid_source_sha256':digest(grid),'method':'first_panel_fixed_square_80',
           'crop_fraction':.8,'crop_anchor':'top_center','crop_box':list(box),'tile_size':list(tile.size),
           'head_sha256':digest(target),'origin':'current_album_sticker',
           'caption_erasing':False,'head_contour_mask':False,'adaptive_recrop':False,
           'normal_chroma_key_only':True,'generation_calls':0}
    (root/'头像裁切.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--episode-dir',required=True,type=Path);p.add_argument('--index',default=1,type=int)
    a=p.parse_args();print(crop_head(a.episode_dir,a.index))
