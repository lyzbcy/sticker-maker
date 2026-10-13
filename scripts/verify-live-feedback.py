"""One marked live acceptance message, no user logs; duplicate checks reuse its receipt."""
import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:os.environ.pop(key,None)
endpoint='https://111.231.25.152:8443/sticker-maker-feedback/feedback'
sample='验收测试：表情包一键制作反馈转发与桌面界面验证。仅模拟数据，无用户日志或作品，请忽略。'
folder=root/'verification/feedback-live';folder.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,STICKER_FEEDBACK_URL=endpoint,STICKER_DESKTOP_USER_DATA=str(folder/'desktop'),STICKER_ENGINE_USER_DATA=str(folder/'engine'),STICKER_ENGINE_NO_LOCK='1')
proc=subprocess.Popen([str(root/'desktop/release/win-unpacked/表情包一键制作.exe'),'--remote-debugging-port=9489'],env=env,stdout=open(folder/'stdout.txt','w'),stderr=open(folder/'stderr.txt','w'))
try:
 with sync_playwright() as p:
  for i in range(40):
   try:browser=p.chromium.connect_over_cdp('http://127.0.0.1:9489');break
   except Exception:
    if i==39:raise
    time.sleep(.5)
  page=browser.contexts[0].pages[0];page.wait_for_timeout(3000)
  page.get_by_role('button',name='遇到问题反馈',exact=True).click()
  page.locator('.feedback textarea').fill(sample)
  page.locator('.feedback input[type=checkbox]').uncheck()
  page.get_by_role('button',name='发送给作者',exact=True).click()
  status=page.locator('.feedback [role=status]')
  for i in range(70):
   if status.inner_text():break
   page.wait_for_timeout(1000)
  text=status.inner_text();page.screenshot(path=str(folder/'feedback-live.png'))
  assert '已送达作者' in text,text
  assert page.locator('.feedback textarea').input_value()=='','successful draft not cleared'
 content='表情包一键制作 0.5.1\n使用问题\n'+sample+'\n'
 digest=hashlib.sha256(content.encode()).hexdigest()
 query=f"import sqlite3,json;d=sqlite3.connect('file:/var/lib/sticker-feedback/receipts.sqlite3?mode=ro',uri=True);r=d.execute('SELECT id,state FROM receipts WHERE digest=? ORDER BY created DESC LIMIT 1',('{digest}',)).fetchone();print(json.dumps(r))"
 command="sudo python3 -c '"+query.replace("'","'\\''")+"'"
 record=json.loads(subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-i',str(Path.home()/'.ssh/id_ed25519'),'ubuntu@111.231.25.152',command],encoding='utf-8'))
 assert record and record[1]=='delivered',record
 body=json.dumps({'request_id':record[0],'msgtype':'text','text':{'content':content}},ensure_ascii=False).encode()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(urllib.request.Request(endpoint,data=body,headers={'Content-Type':'application/json'}),timeout=15) as response:duplicate=json.load(response)
 assert duplicate['errcode']==0 and duplicate['duplicate'] is True,duplicate
 result={'status':'LIVE_FEEDBACK_PASS','sample':sample,'logs_sent':False,'ui_status':text,'request_id':record[0],'receipt_state':record[1],'duplicate_check':duplicate,'live_batches_sent':1,'upstream_business_ack':True}
 (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('LIVE_FEEDBACK_PASS desktop_ui=delivered upstream_business_ack=0 duplicate=receipt_only user_logs=not_sent live_batches=1')
finally:
 proc.terminate();proc.wait(timeout=30)
