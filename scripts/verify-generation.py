from pathlib import Path
import subprocess,os,json,time
root=Path(__file__).resolve().parents[1]
data=root/'verification/native-install'
env=dict(os.environ,STICKER_ENGINE_USER_DATA=str(data),STICKER_ENGINE_NO_LOCK='1',PYTHONPATH=str(root/'sticker_engine'))
for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:env.pop(key,None)
# Only this isolated test library is changed; no platform account is configured.
proc=subprocess.Popen([str(root/'sticker_engine/.venv/Scripts/python.exe'),"-m","sticker_engine.cli"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=open(root/'verification/generation.stderr.txt','w',encoding='utf-8'),text=True,encoding='utf-8',env=env,creationflags=subprocess.CREATE_NO_WINDOW)
log=open(root/'verification/generation.stdout.txt','w',encoding='utf-8')
def request(id,cmd,args={}):
 proc.stdin.write(json.dumps({'id':id,'cmd':cmd,'args':args},ensure_ascii=False)+'\n');proc.stdin.flush()
 for line in proc.stdout:
  log.write(line);log.flush();ev=json.loads(line)
  if ev.get('type')=='progress':print(ev.get('message','')[-180:],flush=True)
  if ev.get('id')==id and ev.get('type') in {'result','error'}:return ev
 raise RuntimeError('engine exited unexpectedly')
try:
 status=request('status','check_codex');print('CODEX_STATUS',json.dumps(status,ensure_ascii=False),flush=True)
 assert status.get('data',{}).get('image_ready'), 'account not ready'
 prefs=request('prefs','load_prefs')['data']['prefs'] or {}
 prefs.update({'grid_size':4,'mode_probs':{'single':1,'duo':0,'trio':0,'quad':0},'story_mode':False,'ref_lib_priority':False,'vision_calls':False,'single_char_probs':{'星星布丁':1},'default_series_id':None})
 saved=request('save','save_prefs',{'prefs':prefs});assert saved['status']=='ok',saved
 result=request('generate','run');print('GENERATION_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
 (root/'verification/generation-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 assert result['status']=='ok',result
 exported=request('export','export_episode',{'path':result['data']['episode_dir'],'destination':str(root/'verification/generated-stickers.zip')})
 print('EXPORT_RESULT',json.dumps(exported,ensure_ascii=False),flush=True)
 assert exported['status']=='ok',exported
 print('REAL_GENERATION_AND_EXPORT_PASS; platform_submission=not_requested; sample_only',flush=True)
finally:
 proc.stdin.close();proc.wait(timeout=45);log.close()

