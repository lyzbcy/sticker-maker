import shutil, os
from pathlib import Path

base = r'E:\星星布丁\微信表情包\星星布丁第5弹'
src_dir = os.path.join(base, '原图_透明ChromaKey')
dst_dir = os.path.join(base, '最终版')
os.makedirs(dst_dir, exist_ok=True)

meanings = {1: '那我问你', 2: '懒懒的', 3: '微笑', 4: '生气', 5: '不',
            6: '打你', 7: '大叫', 8: '帅气', 9: '晕倒'}

for idx, meaning in sorted(meanings.items()):
    src = os.path.join(src_dir, 'frame_%02d.png' % idx)
    if os.path.exists(src):
        dst = os.path.join(dst_dir, meaning + '.png')
        shutil.copy2(src, dst)
        print('frame_%02d.png -> %s.png' % (idx, meaning))
    else:
        print('MISSING: %s' % src)

print('Done. Final count: %d' % len(list(Path(dst_dir).glob('*.png'))))
