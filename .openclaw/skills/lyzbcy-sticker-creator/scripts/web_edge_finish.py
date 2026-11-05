"""Chroma edge decontamination and antialiased white die-cut border."""
import numpy as np
from PIL import Image
from scipy import ndimage
from web_source import PROJECT_ROOT
from sticker_engine.providers.chromakey import ChromaKeyProvider

def clean_key_edges(image,key):
    rgba=ChromaKeyProvider().remove_key(image,key)
    arr=np.asarray(rgba).copy(); rgb=arr[:,:,:3].astype(float)
    bg=arr[:,:,3]==0
    hsv=np.asarray(image.convert('HSV')).astype(float)
    center=212.5 if key=='#ff00ff' else 85.0
    dh=np.abs(hsv[:,:,0]-center);dh=np.minimum(dh,255-dh)
    tinted=(dh<26)&(hsv[:,:,1]>30)
    solid=~ndimage.binary_dilation(bg,iterations=2)&~tinted
    if not solid.any():raise ValueError('No stable foreground to estimate matte')
    _,idx=ndimage.distance_transform_edt(~solid,return_indices=True)
    fg=rgb[idx[0],idx[1]]
    background=np.array([255,0,255] if key=='#ff00ff' else [0,255,0],dtype=float)
    delta=fg-background;den=(delta*delta).sum(axis=2)
    alpha=np.clip(((rgb-background)*delta).sum(axis=2)/np.maximum(den,1),0,1)
    edge=ndimage.binary_dilation(bg,iterations=3)&~bg&tinted
    unmixed=np.clip((rgb-(1-alpha[:,:,None])*background)/np.maximum(alpha[:,:,None],.03),0,255)
    arr[:,:,:3][edge]=unmixed[edge].astype('uint8')
    arr[:,:,3][edge]=np.round(alpha[edge]*255).astype('uint8')
    arr[bg]=0
    return Image.fromarray(arr)

def white_outline(image,width=2):
    if width<=0:return image
    scale=3;large=image.resize((image.width*scale,image.height*scale),Image.Resampling.LANCZOS)
    radius=max(1,round(width*scale));yy,xx=np.ogrid[-radius:radius+1,-radius:radius+1]
    footprint=xx*xx+yy*yy<=radius*radius
    alpha=np.asarray(large)[:,:,3]
    expanded=ndimage.maximum_filter(alpha,footprint=footprint)
    white=Image.new('RGBA',large.size,'white');white.putalpha(Image.fromarray(expanded))
    white.alpha_composite(large)
    return white.resize(image.size,Image.Resampling.LANCZOS)
