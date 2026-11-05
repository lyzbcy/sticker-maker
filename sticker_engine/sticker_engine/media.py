"""Final sticker discovery and lossless animated-upload validation."""
from pathlib import Path

def final_stickers(directory):
    directory = Path(directory)
    return sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ('.png', '.gif')), key=lambda p: p.stem) if directory.is_dir() else []

def sticker_type(paths):
    suffixes = {p.suffix.lower() for p in paths}
    if suffixes == {'.gif'}:
        return 'dynamic'
    return 'mixed' if '.gif' in suffixes else 'static'

def validate_dynamic(paths):
    from PIL import Image
    import hashlib
    problems = []
    if len(paths) not in (8, 16, 24):
        problems.append('动态表情数量必须为8、16或24张')
    seen = set()
    for path in paths:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                problems.append(f'动态表情字节重复：{path.name}')
            seen.add(digest)
            if path.stat().st_size > 500 * 1024:
                problems.append(f'动态表情超过500KiB：{path.name}')
            with Image.open(path) as im:
                if im.format != 'GIF' or im.size != (240, 240) or getattr(im, 'n_frames', 1) < 2:
                    problems.append(f'须为240×240多帧GIF：{path.name}')
                if im.info.get('loop') != 0:
                    problems.append(f'动态表情须无限循环：{path.name}')
                for i in range(getattr(im, 'n_frames', 1)):
                    im.seek(i)
                    im.load()
                    if im.info.get('duration', 0) <= 0:
                        problems.append(f'动态帧时长无效：{path.name}')
                        break
        except (OSError, ValueError, EOFError) as exc:
            problems.append(f'GIF解码失败：{path.name}（{exc}）')
    return problems
