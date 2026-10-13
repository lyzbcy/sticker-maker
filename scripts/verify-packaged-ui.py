import subprocess,os,time,json,sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from playwright.sync_api import sync_playwright
for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:os.environ.pop(key,None)
root=Path.cwd();data=root/'verification/packaged-profile';data.mkdir(exist_ok=True)
env=dict(os.environ,STICKER_DESKTOP_USER_DATA=str(data/'desktop'),STICKER_ENGINE_USER_DATA=str(data/'engine'),STICKER_ENGINE_NO_LOCK='1')
exe=Path(sys.argv[1]) if len(sys.argv)>1 else root/'desktop/release/win-unpacked/表情包一键制作.exe'
proc=subprocess.Popen([str(exe),'--remote-debugging-port=9489'],env=env,stdout=open(data/'stdout.txt','w'),stderr=open(data/'stderr.txt','w'))
try:
 with sync_playwright() as p:
  for i in range(40):
   try:browser=p.chromium.connect_over_cdp('http://127.0.0.1:9489');break
   except Exception as e:
    if i==39:raise
    time.sleep(.5)
  page=browser.contexts[0].pages[0];errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.wait_for_timeout(4500)
  text=page.locator('body').inner_text();(data/'page.txt').write_text(text,encoding='utf-8')
  page.screenshot(path=str(root/'verification/packaged-app.png'))
  assert len(text)>80,text
  assert not errors,errors
  assert page.evaluate('document.visibilityState')=='visible','installed application window is hidden'
  print(json.dumps({'status':'PACKAGED_UI_PASS','visible_text_length':len(text),'page_errors':errors,'title':page.title(),'own_process_pid':proc.pid},ensure_ascii=False))
finally:
 proc.terminate();proc.wait(timeout=30)
