"""Read-only byte-duplicate audit for an explicitly selected local sticker."""
from pathlib import Path
import hashlib

def duplicate_sources(source, candidates, root):
    root=Path(root).resolve(); source=Path(source).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError('请选择当前资源库中的真实表情文件')
    if source.suffix.lower() not in ('.png','.gif','.webp','.jpg','.jpeg'):
        raise ValueError('请选择表情图片')
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()
    sha=digest(source);matches=[];seen={source};checked=0;skipped=0
    for candidate in candidates:
        p=Path(candidate).resolve()
        if p in seen:continue
        seen.add(p)
        if not p.is_relative_to(root) or not p.is_file():skipped+=1;continue
        try:
            checked+=1
            if p.stat().st_size==source.stat().st_size and digest(p)==sha:matches.append(str(p))
        except OSError:skipped+=1
    return {'source':str(source),'sha256':sha,'matches':matches,'checked':checked,'skipped':skipped,
            'kind':'exact-bytes-only','platform_duplicate_status':'unknown'}
