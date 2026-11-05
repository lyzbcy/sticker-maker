"""Crop original pixels from THIS album's sticker; never from a shared base portrait."""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image, ImageOps

def crop_head(root, index, polygon=None, rect=None, caption_regions=None):
    root=Path(root)
    manifest=json.loads((root/'成品清单.json').read_text(encoding='utf-8'))
    item=next(x for x in manifest['files'] if x['index']==index)
    source=root/item['file']
    source.resolve().relative_to((root/'最终版').resolve())
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=item['sha256']:raise ValueError('Source sticker changed after review')
    # User correction: natural square framing, retaining shoulders/upper body.
    # A legacy polygon is treated only as a bounding rectangle, never a matte.
    if rect is None and polygon:
        rect=[min(x for x,y in polygon),min(y for x,y in polygon),max(x for x,y in polygon),max(y for x,y in polygon)]
    if not rect or len(rect)!=4 or not all(0<=v<=1 for v in rect) or rect[0]>=rect[2] or rect[1]>=rect[3]:
        raise ValueError('Supply a reviewed rectangle retaining complete head and natural upper body')
    im=Image.open(source).convert('RGBA')
    im=im.crop((round(rect[0]*im.width),round(rect[1]*im.height),round(rect[2]*im.width),round(rect[3]*im.height)))
    # Remove disconnected caption/decorations near the top, without a head
    # contour mask or cutting away shoulders/arms. Limit border separation to
    # the upper half so a white garment is not treated as a caption border.
    import numpy as np
    from scipy import ndimage
    arr=np.asarray(im).copy();rgb=arr[:,:,:3].astype(int);alpha=arr[:,:,3]
    upper=np.indices(alpha.shape)[0]<im.height*.5
    for region in caption_regions or []:
        if len(region)!=4 or not all(0<=v<=1 for v in region) or region[0]>=region[2] or region[1]>=region[3]:
            raise ValueError('Invalid caption cleanup rectangle')
        x0,y0,x1,y1=region
        upper[round(y0*im.height):round(y1*im.height),round(x0*im.width):round(x1*im.width)]=True
    white=(rgb.min(axis=2)>=215)&((rgb.max(axis=2)-rgb.min(axis=2))<28)&(alpha>0)&upper
    edge=ndimage.binary_dilation(alpha==0)
    border=ndimage.binary_propagation(white&edge,mask=white);arr[:,:,3][border]=0
    labels,n=ndimage.label(arr[:,:,3]>8)
    if n>1:
        sizes=np.bincount(labels.ravel());sizes[0]=0;arr[:,:,3][labels!=int(sizes.argmax())]=0
    im=Image.fromarray(arr)
    bbox=im.getbbox()
    if not bbox:raise ValueError('Empty head selection')
    head=ImageOps.contain(im.crop(bbox),(540,540),Image.Resampling.LANCZOS)
    out=Image.new('RGBA',(600,600));out.alpha_composite(head,((600-head.width)//2,(600-head.height)//2))
    target=root/'原图/_noword/封面头像源.png';target.parent.mkdir(parents=True,exist_ok=True);out.save(target)
    proof={'source':item['file'],'panel_index':index,'source_sha256':digest,'rect':rect,'caption_regions':caption_regions,'framing':'natural_head_and_upper_body',
           'head_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'origin':'current_album_sticker',
           'visual_review_required':True,'generation_calls':0}
    (root/'头像裁切.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--episode-dir',required=True,type=Path)
    p.add_argument('--index',required=True,type=int);p.add_argument('--rect');p.add_argument('--polygon');p.add_argument('--caption-regions')
    a=p.parse_args();print(crop_head(a.episode_dir,a.index,json.loads(a.polygon) if a.polygon else None,json.loads(a.rect) if a.rect else None,json.loads(a.caption_regions) if a.caption_regions else None))
