"""Download immutable official 0.5.1 assets and verify actual bytes, not candidate hashes."""
import hashlib, json, os, plistlib, subprocess, urllib.request, zipfile, uuid, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']: os.environ.pop(key, None)
folder = Path('verification/final-release'); folder.mkdir(parents=True, exist_ok=True)
release = json.loads(subprocess.check_output(['gh', 'release', 'view', 'v0.5.1', '--json', 'tagName,isDraft,isPrerelease,assets'], encoding='utf-8'))
assert not release['isDraft'] and not release['isPrerelease']
results = []
from verified_download import digest_file, download_ranges
for name in ['sticker-maker-win-v0.5.1-setup.exe', 'sticker-maker-mac-v0.5.1.zip']:
    asset = next(x for x in release['assets'] if x['name'] == name)
    size = asset['size']; assert 0 < size < 1024**3
    expected = asset['digest'].removeprefix('sha256:'); assert len(expected) == 64
    dest = folder / name
    if not dest.exists() or dest.stat().st_size != size or digest_file(dest) != expected:
        download_ranges('https://github.com/lyzbcy/sticker-maker/releases/download/v0.5.1/' + name, dest, size, expected)
    if name.endswith('.zip'):
        # ditto stores UTF-8 filenames without consistently setting the UTF-8 bit.
        with zipfile.ZipFile(dest, metadata_encoding='utf-8') as z:
            assert z.testzip() is None
            info = '表情包一键制作.app/Contents/Info.plist'
            assert plistlib.loads(z.read(info))['CFBundleShortVersionString'] == '0.5.1'
            assert 'install.command' in z.namelist()
    else:
        with dest.open('rb') as stream: assert stream.read(2) == b'MZ'
    result = {'file':str(dest.resolve()), 'name':name, 'version':'0.5.1', 'sha256':expected, 'sizeBytes':size, 'result':'PUBLIC_DOWNLOAD_HASH_PASS'}
    results.append(result); print(name + ' PUBLIC_DOWNLOAD_HASH_PASS sha256=' + expected, flush=True)
(folder/'release-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
