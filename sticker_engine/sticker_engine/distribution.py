"""Local export: only artwork below the configured workspace, never credentials."""
from pathlib import Path
import zipfile
import os
import tempfile

def export_episode(source, destination, output_root):
    source=Path(source).resolve(strict=True);root=Path(output_root).resolve()
    if source == root or root not in source.parents or not source.is_dir():
        raise ValueError('请选择当前作品库中的作品')
    target=Path(destination).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    allowed={'最终版','横幅','封面','图标','赞赏图'}
    files=[]
    for directory in allowed:
        folder=source/directory
        if folder.is_symlink(): raise ValueError('作品包含链接路径，请重新生成后保存')
        if not folder.is_dir(): continue
        for file in folder.iterdir():
            if file.is_symlink(): raise ValueError('作品包含链接文件')
            if file.is_file() and file.suffix.lower() in {'.png','.jpg','.jpeg','.gif'}:
                files.append(file)
    if not any(f.parent.name == '最终版' for f in files): raise ValueError('这组作品还没有完成的表情图片')
    fd,name=tempfile.mkstemp(prefix='.sticker-export-',suffix='.zip',dir=target.parent);os.close(fd)
    try:
        with zipfile.ZipFile(name,'w',zipfile.ZIP_DEFLATED) as z:
            for file in sorted(files):z.write(file,file.relative_to(source).as_posix())
            z.writestr('使用说明.txt','表情包一键制作：最终版目录是表情图片，可按需要添加到聊天软件。素材目录供微信开放平台投稿。投稿不等于审核通过。')
        os.replace(name,target)
    finally:
        if Path(name).exists():Path(name).unlink()
    return {'path':str(target),'images':len(files)}
