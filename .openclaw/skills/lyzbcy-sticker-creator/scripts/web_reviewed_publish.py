"""Submit only visually approved run items and retain mutation checkpoints for reconciliation."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright
repo=Path(__file__).resolve().parents[4]
parser=argparse.ArgumentParser(description='Publish visually approved albums with the existing WeChat SDK')
parser.add_argument('--run',required=True,type=Path)
out=parser.parse_args().run.resolve()
if not out.is_relative_to(repo/'outputs'):
    raise ValueError('Run directory must be under project outputs')
pub=repo/'.openclaw/skills/lyzbcy-sticker-publisher/scripts'
sys.path.insert(0,str(repo/'sticker_engine'))
from sticker_engine.publish.browser import BrowserSession
from sticker_engine.publish.config import PublishConfig
from sticker_engine.publish.platform_data import LIST_URL,read_json,read_detail
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):
    tmp=p.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(p)
def stage(r):
    n=r['number']; source=Path(r['path']); target=out/'投稿副本'/str(n)
    if target.exists(): return target
    target.parent.mkdir(exist_ok=True)
    staging=target.with_name(f'{n}-准备中-{uuid.uuid4().hex[:6]}')
    shutil.copytree(source,staging)
    old=read(staging/'成品清单.json')
    proof=read(staging/'头像裁切.json')
    words=r['candidate_words']
    for row in old['files']:
        i=row['index']; original=staging/row['file']; new=original.with_name(words[i-1]+'.png')
        original.rename(new)
        if Path(proof['source'])==Path(row['file']):
            proof['source']=str(new.relative_to(staging))
        row['file']=str(new.relative_to(staging))
        row['meaning']=words[i-1]
    write(staging/'头像裁切.json',proof)
    write(staging/'成品清单.json',old)
    write(staging/'meanings.json',{i+1:v for i,v in enumerate(words)})
    recipe=read(staging/'发布素材清单.json')
    write(staging/'发布素材复核.json',{'approved':True,'role':r['album']['role'],'portrait_reviewed':True,
          'asset_hashes':{f['path']:f['sha256'] for f in recipe['files']},
          'review_evidence':str(out/'审图板'/f'{n}.jpg'),'review_source':'Codex逐格视觉复核'})
    staging.rename(target)
    return target
def emit(s): print(s,flush=True)
def run():
    from datetime import datetime
    boundary=read(out/'运行边界.json') if (out/'运行边界.json').exists() else {}
    deadline=datetime.fromisoformat(boundary['deadline']) if boundary.get('deadline') else None
    def can_start_submission():
        return not deadline or (deadline-datetime.now(deadline.tzinfo)).total_seconds()>=180
    if not can_start_submission():
        emit('到截止前3分钟，停止启动新投稿')
        return
    decisions=read(out/'视觉复核.json')
    chosen=[r for r in read(out/'审图状态.json')['items'] if decisions.get(str(r['number'])) is True]
    jobs=out/'投稿回执'; jobs.mkdir(exist_ok=True)
    selected=[]
    for r in chosen:
        n=r['number']; p=jobs/f'{n}.json'
        if p.exists(): continue
        t=stage(r)
        preflight=subprocess.run([sys.executable,'-X','utf8',str(pub/'web_preflight.py'),'--episode-dir',str(t),'--role',r['album']['role']],
            capture_output=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        if preflight.returncode:
            write(p,{'state':'preflight_failed','name':r['name'],'error':preflight.stdout[-4500:] or preflight.stderr[-700:]})
            emit(f'{n} 本地投稿预检未通过')
            continue
        selected.append((r,t))
    if not selected:return
    with sync_playwright() as pw:
        session=BrowserSession(PublishConfig(),playwright=pw)
        try:
            page=session.start(headless=True)
            if not session.ensure_login(page,on_status=emit):
                raise RuntimeError(session.last_login_error)
            baseline=read_json(page,LIST_URL)['List']
            page.goto('https://sticker.weixin.qq.com/cgi-bin/mmemoticonwebnode-bin/pages/stickerPage/detail',wait_until='domcontentloaded',timeout=25000)
            page.wait_for_function(r"[...document.scripts].some(s=>/\/assets\/index-[^/]+\.js$/.test(s.src))",timeout=15000)
            for r,t in selected:
                if not can_start_submission():
                    emit('到截止前3分钟，剩余已审稿留待下一轮')
                    break
                page.goto('https://sticker.weixin.qq.com/cgi-bin/mmemoticonwebnode-bin/pages/stickerPage/detail',wait_until='domcontentloaded',timeout=25000)
                page.wait_for_function(r"[...document.scripts].some(s=>/\/assets\/index-[^/]+\.js$/.test(s.src))",timeout=15000)
                n=r['number']; album={k:r['album'][k] for k in ('episode','name','role','priceBeans')}
                album['dir']=str(t)
                p=jobs/f'{n}.json'
                if any(x['Name'].replace(' ','')==album['name'] for x in baseline):
                    write(p,{'state':'already_exists','name':r['name']})
                    continue
                key='__stickerAudit'+uuid.uuid4().hex[:12]
                builder="const m=require(process.argv[1]); const a=JSON.parse(process.argv[2]);m.inputs(a).then(v=>process.stdout.write(m.browserPublish([v],process.argv[3],4,false))).catch(e=>{console.error(e.message);process.exitCode=1})"
                source=subprocess.check_output(['node','-e',builder,str(pub/'web_sdk_publish.cjs'),json.dumps(album,ensure_ascii=False),key],
                                               encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
                write(p,{'state':'intent','name':r['name'],'events':[]})
                page.evaluate('() => {window["'+key+'"]={state:"running"};void (async()=>{try{const result=await(async()=>{'+source+'})();Object.assign(window["'+key+'"],{state:"done",result});}catch(e){Object.assign(window["'+key+'"],{state:"error",error:String(e)});}})()}')
                until=time.monotonic()+150
                event_count=0
                while time.monotonic()<until:
                    state=page.evaluate('(key)=>window[key]',key)
                    events=state.get('events',[])
                    state['name']=r['name']
                    if len(events)>event_count or state['state']!='running':
                        write(p,state)
                        event_count=len(events)
                        page.evaluate('([key,n])=>{window[key].ack=n}',[key,event_count])
                    if state['state']!='running':break
                    time.sleep(.22)
                if state['state']=='done':
                    receipt=state['result'][0]
                    emit(f"{n} 已提审 {receipt['id']} 状态 {receipt['status']}")
                    continue
                emit(f'{n} {state["state"]} {str(state.get("error","超时"))[:180]}')
                if any(e['event']=='create_intent' for e in events) or state['state']=='running':
                    raise RuntimeError(f'{n} 投稿结果待核销，已保留原日志')
        finally:
            session.close()
if __name__ == '__main__':
    run()
