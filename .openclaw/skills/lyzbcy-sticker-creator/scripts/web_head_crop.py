"""Crop original pixels from THIS album's sticker; never from a shared base portrait."""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps

def crop_head(root, index, polygon):
    root=Path(root)
    manifest=json.loads((root/'成品清单.json').read_text(encoding='utf-8'))
    item=next(x for x in manifest['files'] if x['index']==index)
    source=root/item['file']
    source.resolve().relative_to((root/'最终版').resolve())
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=item['sha256']:raise ValueError('Source sticker changed after review')
    if len(polygon)<3 or any(len(p)!=2 or not all(0<=v<=1 for v in p) for p in polygon):
        raise ValueError('Supply reviewed normalized head polygon, including full face and hair')
    im=Image.open(source).convert('RGBA');mask=Image.new('L',im.size)
    ImageDraw.Draw(mask).polygon([(round(x*im.width),round(y*im.height)) for x,y in polygon],fill=255)
    from PIL import ImageChops
    im.putalpha(ImageChops.multiply(im.getchannel('A'),mask.filter(ImageFilter.GaussianBlur(.45))))
    # Sticker white die-cut borders do not belong in the store portrait. Remove
    # only near-white pixels connected to the outside, retaining isolated eyes.
    import numpy as np
    from scipy import ndimage
    arr=np.asarray(im).copy();rgb=arr[:,:,:3].astype(int);alpha=arr[:,:,3]
    white=(rgb.min(axis=2)>=215)&((rgb.max(axis=2)-rgb.min(axis=2))<28)&(alpha>0)
    outside=ndimage.binary_dilation(alpha==0)
    border=ndimage.binary_propagation(white&outside,mask=white)
    arr[:,:,3][border]=0;im=Image.fromarray(arr)
    bbox=im.getbbox()
    if not bbox:raise ValueError('Empty head selection')
    head=ImageOps.contain(im.crop(bbox),(540,540),Image.Resampling.LANCZOS)
    out=Image.new('RGBA',(600,600));out.alpha_composite(head,((600-head.width)//2,(600-head.height)//2))
    target=root/'原图/_noword/封面头像源.png';target.parent.mkdir(parents=True,exist_ok=True);out.save(target)
    proof={'source':item['file'],'panel_index':index,'source_sha256':digest,'polygon':polygon,
           'head_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'origin':'current_album_sticker',
           'visual_review_required':True,'generation_calls':0}
    (root/'头像裁切.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--episode-dir',required=True,type=Path)
    p.add_argument('--index',required=True,type=int);p.add_argument('--polygon',required=True)
    a=p.parse_args();print(crop_head(a.episode_dir,a.index,json.loads(a.polygon)))
