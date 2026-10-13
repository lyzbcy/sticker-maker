"""Bounded resumable public release download; final complete SHA is mandatory."""
import hashlib,urllib.request,uuid,time
from concurrent.futures import ThreadPoolExecutor
def digest_file(file):
    h = hashlib.sha256()
    with file.open('rb') as stream:
        while chunk := stream.read(1024*1024): h.update(chunk)
    return h.hexdigest()
def download_ranges(url, dest, size, expected):
    folder = dest.parent
    temp = dest.with_suffix(dest.suffix + '.part')
    if dest.exists() and dest.stat().st_size < size and not temp.exists(): dest.rename(temp)
    prefix = temp.stat().st_size if temp.exists() else 0
    assert prefix <= size
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
        resolved = response.geturl()
        assert response.status == 200 and int(response.headers['Content-Length']) == size
    segments = [(start, min(size-1, start+16*1024*1024-1)) for start in range(prefix, size, 16*1024*1024)]
    def segment(span):
        start,end = span; part = folder / (dest.name + '.range-' + str(start))
        if part.exists() and part.stat().st_size == end-start+1: return part
        for attempt in range(3):
            try:
                request = urllib.request.Request(resolved+'&range_nonce='+uuid.uuid4().hex, headers={'Range':f'bytes={start}-{end}', 'Cache-Control':'no-cache'})
                with urllib.request.urlopen(request, timeout=30) as response, part.open('wb') as output:
                    assert response.status == 206 and response.headers.get('Content-Range') == f'bytes {start}-{end}/{size}'
                    total = 0
                    while chunk := response.read(65536):
                        total += len(chunk); assert total <= end-start+1; output.write(chunk)
                assert total == end-start+1
                return part
            except Exception:
                if attempt == 2: raise
                time.sleep(2)
    with ThreadPoolExecutor(max_workers=6) as pool: parts = list(pool.map(segment, segments))
    assembled = dest.with_suffix(dest.suffix+'.verified')
    h = hashlib.sha256(); total = 0
    with assembled.open('wb') as output:
        for part in ([temp] if prefix else []) + parts:
            with part.open('rb') as stream:
                while chunk := stream.read(1024*1024): total += len(chunk); h.update(chunk); output.write(chunk)
    assert total == size and h.hexdigest() == expected, 'public asset bytes mismatch'
    assembled.replace(dest)
