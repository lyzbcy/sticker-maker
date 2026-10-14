from PIL import Image, ImageDraw
import numpy as np
from sticker_engine.stages.assets import make_big_head_cover


def test_wide_portrait_preserves_hair_ears_and_chin(tmp_path):
    im=Image.new('RGBA',(240,240));d=ImageDraw.Draw(im)
    d.ellipse((15,20,224,219),fill=(40,80,180,255))
    d.rectangle((15,90,25,110),fill=(255,0,0,255))
    d.rectangle((214,90,224,110),fill=(0,255,0,255))
    d.rectangle((110,209,130,219),fill=(255,200,0,255))
    src=tmp_path/'portrait.png';im.save(src);out=tmp_path/'cover.png'
    assert make_big_head_cover(src,out)
    a=np.array(Image.open(out))
    assert ((a[:,:,0]>200)&(a[:,:,1]<30)&(a[:,:,2]<30)).any()
    assert ((a[:,:,1]>200)&(a[:,:,0]<30)&(a[:,:,2]<30)).any()
    assert ((a[:,:,0]>200)&(a[:,:,1]>150)&(a[:,:,2]<30)).any()
    assert not a[0,:,3].any() and not a[:,-1,3].any()
