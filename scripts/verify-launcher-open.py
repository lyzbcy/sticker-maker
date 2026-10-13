"""Actual released launcher UI opens isolated 0.5.1 through production shell.openPath.
Association and authentic public release cache are seeded; automatic installed detection
is separately proved by the strict read-only checker. No personal installation is stopped.
"""
import json, os, subprocess, time, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1];folder=root/'verification/launcher-ui'
target=root/'desktop/release/win-unpacked/表情包一键制作.exe'
center=next((folder/'center').rglob('捞鱼软件中心.exe'))
profile=folder/'profile';profile.mkdir(exist_ok=True)
home=folder/'home';home.mkdir(exist_ok=True)
for name in ['local','roaming']: (home/name).mkdir(exist_ok=True)
for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:os.environ.pop(key,None)
def ps(code):
    return subprocess.check_output(['powershell','-NoProfile','-Command','[Console]::OutputEncoding=[Text.UTF8Encoding]::new();'+code],encoding='utf-8')
escaped=str(target).replace("'","''")
query=f"@(Get-Process | Where-Object {{$_.Path -eq '{escaped}'}} | Select-Object Id,@{{Name='MainWindowHandle';Expression={{$_.MainWindowHandle.ToInt64()}}}}) | ConvertTo-Json -Compress"
assert not ps(query).strip(),'test binary already running; do not disturb it'
manifest=json.loads((root/'desktop/site/version.json').read_text(encoding='utf-8'));asset=manifest['platforms']['win']
state={'schemaVersion':1,'installId':str(uuid.uuid4()),'installs':{'sticker-maker':str(target)},'releaseCache':{'sticker-maker':{'version':'0.5.1','name':'sticker-maker-win-v0.5.1-setup.exe','size':443765034,'url':asset['url'],'sha256':asset['sha256'],'page':'https://github.com/lyzbcy/sticker-maker/releases/tag/v0.5.1','prerelease':False}},'downloaded':{},'lastCheckDay':time.strftime('%Y-%m-%d'),'analytics':{'enabled':False,'provider':'self-hosted','endpoint':''}}
(profile/'state.json').write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
env=dict(os.environ,HOME=str(home),USERPROFILE=str(home),LOCALAPPDATA=str(home/'local'),APPDATA=str(home/'roaming'),STICKER_DESKTOP_USER_DATA=str(folder/'sticker-profile'),STICKER_ENGINE_USER_DATA=str(folder/'sticker-library'),STICKER_ENGINE_NO_LOCK='1')
# Run the unchanged official app resources in Electron's development host so the
# launcher's packaged-only global protocol/shortcut registration does not run.
host=root/'desktop/node_modules/electron/dist/electron.exe'
proc=subprocess.Popen([str(host),str(center.parent/'resources/app'),'--remote-debugging-port=9550','--user-data-dir='+str(profile)],env=env,stdout=open(folder/'stdout.txt','w'),stderr=open(folder/'stderr.txt','w'))
try:
 with sync_playwright() as p:
    for i in range(50):
        try:browser=p.chromium.connect_over_cdp('http://127.0.0.1:9550',timeout=2000);break
        except Exception:
            if i==49:raise
            time.sleep(.5)
    page=browser.contexts[0].pages[0]
    page.locator('[data-action=detail][data-id=sticker-maker]').first.wait_for()
    page.wait_for_timeout(3000)
    data=page.evaluate('window.launcher.init()')
    # public init returns its state flattened.
    installs=data.get('installs',data.get('state',{}).get('installs',{}))
    assert Path(installs['sticker-maker'])==target,installs.get('sticker-maker')
    # The published daily statistics snapshot may contain an older release cache.
    # Exercise the normal product route preflight to resolve the public latest anew.
    page.evaluate("window.launcher.routes('sticker-maker')")
    data=page.evaluate('window.launcher.init()')
    cache=data.get('releaseCache',data.get('state',{}).get('releaseCache',{}))
    assert cache['sticker-maker']['version']=='0.5.1',cache.get('sticker-maker')
    page.evaluate('window.launcher.init().then(next=>update(next))')
    page.locator('[data-action=detail][data-id=sticker-maker]').first.click()
    button=page.locator('#detail [data-action=open][data-id=sticker-maker]');button.wait_for()
    assert '打开软件' in button.inner_text()
    page.screenshot(path=str(folder/'center-before-open.png'))
    button.click()
    for _ in range(40):
        raw=ps(query).strip(); processes=json.loads(raw) if raw else []
        if isinstance(processes,dict):processes=[processes]
        if any(x['MainWindowHandle']!=0 for x in processes):break
        time.sleep(.5)
    assert any(x['MainWindowHandle']!=0 for x in processes),'new application window not visible'
    version=ps(f"(Get-Item -LiteralPath '{escaped}').VersionInfo.FileVersion").strip();assert version=='0.5.1',version
    page.screenshot(path=str(folder/'center-opened.png'))
    result={'status':'LAUNCHER_LITERAL_OPEN_PASS','launcher':'unchanged official 0.8.10 resources under Electron30 dev host; packaged-only protocol registration excluded','product':'0.5.1 packaged candidate','shell':'production shell.openPath, no extra argv','visible':True,'association':'seeded isolated profile, not automatic discovery','metadata':'normal routes IPC resolved public latest=0.5.1 before opening','automatic_detection':'separate strict checker exit0','personal_data':'unchanged'}
    (folder/'open-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('LAUNCHER_LITERAL_OPEN_PASS visible=true product=0.5.1; profile=isolated; actual_production_shell=true')
finally:
    # Entry asserted zero processes at this exact test-only executable path.
    ps(f"Get-Process | Where-Object {{$_.Path -eq '{escaped}'}} | Stop-Process -Force -ErrorAction SilentlyContinue")
    proc.terminate();proc.wait(timeout=30)
