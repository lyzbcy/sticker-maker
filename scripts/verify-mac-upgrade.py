"""Actual Mac bundle replacement and failed signature retention, isolated CI only."""
import hashlib, json, os, pathlib, subprocess, time, urllib.request, zipfile

root = pathlib.Path(os.environ['RUNNER_TEMP']).resolve()
stage = root / 'mac-package'
destination = root / 'fan-apps' / '表情包一键制作.app'
old_zip = root / 'old-mac.zip'
urllib.request.urlretrieve('https://github.com/lyzbcy/sticker-maker/releases/download/v0.5.0/sticker-maker-mac-v0.5.0.zip', old_zip)
assert hashlib.sha256(old_zip.read_bytes()).hexdigest() == 'fc60651e13f69406961768b3e586fb4b3222f7f6f8f4c64aac49b3b4807086a8'
old_stage = root / 'old-mac'
subprocess.run(['ditto', '-x', '-k', str(old_zip), str(old_stage)], check=True)
old_app = next(old_stage.rglob('表情包一键制作.app'))
subprocess.run(['rm', '-rf', str(destination)], check=True)  # fixed CI-only verified child
subprocess.run(['ditto', str(old_app), str(destination)], check=True)
binary = destination / 'Contents/MacOS/表情包一键制作'
old_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
profile = root / 'mac-upgrade-profile'
profile.mkdir(exist_ok=True)
sentinel = profile / 'retained-work.txt'
sentinel.write_text('original artwork sentinel')
env = dict(os.environ, STICKER_INSTALL_ROOT=str(destination.parent), STICKER_INSTALL_NO_LAUNCH='1', STICKER_DESKTOP_USER_DATA=str(profile), STICKER_ENGINE_USER_DATA=str(profile / 'library'))
old = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5)
assert old.poll() is None, 'old application exited before handoff'
ready = root / 'mac-upgrade-ready'
helper = subprocess.Popen(['bash', str(stage / 'install.command'), '--update', str(old.pid), str(ready)], env=env)
try:
    for _ in range(100):
        if ready.exists(): break
        time.sleep(.1)
    assert ready.read_text() == 'ready'
finally:
    old.terminate()
    old.wait(timeout=20)
assert helper.wait(timeout=180) == 0
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(destination)], check=True)
assert hashlib.sha256(binary.read_bytes()).hexdigest() != old_hash
backups = list(destination.parent.glob('表情包一键制作.rollback-*.app'))
assert any(hashlib.sha256((x / 'Contents/MacOS/表情包一键制作').read_bytes()).hexdigest() == old_hash for x in backups)
assert sentinel.read_text() == 'original artwork sentinel'
new_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
corrupt = stage / '表情包一键制作.app/Contents/MacOS/表情包一键制作'
with corrupt.open('r+b') as stream:
    stream.seek(4096); byte = stream.read(1); assert byte
    stream.seek(4096); stream.write(bytes([byte[0] ^ 1]))
failed = subprocess.run(['bash', str(stage / 'install.command'), '--update', '999999', str(root / 'mac-failed-ready')], env=env, capture_output=True)
assert failed.returncode != 0, 'corrupt bundle accepted'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == new_hash
assert sentinel.read_text() == 'original artwork sentinel'
import plistlib
version = json.loads(pathlib.Path('desktop/package.json').read_text())['version']
installed_version = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
assert installed_version == version
result = {'status': 'MAC_REPLACEMENT_PASS', 'from': '0.5.0', 'to': installed_version, 'old_bundle_backup': 'hash_verified', 'failed_signature': 'existing_bundle_retained', 'artwork': 'retained', 'automatic_relaunch': 'not_tested_headless', 'failure_exit': failed.returncode}
pathlib.Path('verification/mac-upgrade.json').write_text(json.dumps(result, indent=2))
print(f'MAC_REPLACEMENT_PASS from=0.5.0 to={installed_version}; backup=original_hash; invalid_signature=rejected; artwork=retained')
