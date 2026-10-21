"""Isolated Electron/IPC acceptance. Never opens, edits or posts real artwork.

Run with sticker_engine/.venv/Scripts/python.exe from the repository root.
An optional --app points to an unpacked candidate executable.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from sticker_engine.config.series import EpisodeMeta
from sticker_engine.project import atomic_json,create_project,read_project,seal_project
from sticker_engine.library.runtime import account_key


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app');args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    evidence=repo/'verification/project-storage-20261020'
    evidence.mkdir(parents=True,exist_ok=True)
    task=Path(os.environ['LOCALAPPDATA'])/'StickerMakerBuilds/0.6.0'/('qa-'+uuid.uuid4().hex[:8])
    engine=task/'engine';collection=task/'表情工程';p=collection/'周三涵做表情37'
    p.mkdir(parents=True)
    account=account_key('acceptance-fixture');library=uuid.uuid4().hex
    atomic_json(collection/'projects.json',dict(format='sticker-maker-project-collection',schema_version=1,library_id=library))
    atomic_json(engine/'resource_library/device.json',dict(storage_mode='projects',project_root=str(collection),
        account_id=account,account_label='隔离验收样例',library_id=library,device_id=uuid.uuid4().hex))
    for i in range(1,9):
        f=p/'最终版'/f'词{i}.png';f.parent.mkdir(exist_ok=True)
        Image.new('RGBA',(240,240),(35+i*15,95,65,255)).save(f)
    for name,size in [('封面',(240,240)),('横幅',(750,400)),('图标',(50,50))]:
        f=p/name/(name+'.png');f.parent.mkdir()
        Image.new('RGBA',size,(45,110,75,255)).save(f)
    raw=p/'原图/grid_4x4.png';raw.parent.mkdir();Image.new('RGBA',(1024,1024),(235,220,180,255)).save(raw)
    atomic_json(p/'rating.json',dict(overall=92,note='隔离测试评分',ratings={'词1':dict(score=88,note='人工原值')}))
    create_project(p,EpisodeMeta(work_id='qa-work',account_id=account,account_label='隔离验收样例',
                               album_name=p.name,intro='隔离验收工程，无真实投稿').to_dict(),
                   meanings={str(i):f'词{i}' for i in range(1,9)},characters=['星星布丁'])
    def protected():
        return {str(f.relative_to(collection)):hashlib.sha256(f.read_bytes()).hexdigest()
                for f in collection.rglob('*') if f.is_file() and ('最终版' in f.parts or f.name=='rating.json')}
    before=protected()
    env=dict(os.environ,STICKER_ENGINE_USER_DATA=str(engine),STICKER_DESKTOP_USER_DATA=str(task/'electron'),
             STICKER_DESKTOP_HIDE_WINDOW='1',PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    env.pop('ELECTRON_RUN_AS_NODE',None)
    exe=Path(args.app) if args.app else repo/'desktop/node_modules/electron/dist/electron.exe'
    command=[str(exe)] + ([] if args.app else [str(repo/'desktop')]) + ['--remote-debugging-port=9495',
             '--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']
    log=(evidence/'electron-acceptance.log').open('w',encoding='utf-8')
    proc=subprocess.Popen(command,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    report={'fixture':str(task),'app':str(exe),'packaged':bool(args.app)}
    try:
        with sync_playwright() as pw:
            browser=None
            for _ in range(50):
                try:
                    browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9495');break
                except Exception:
                    if proc.poll() is not None:raise RuntimeError('candidate exited; see electron-acceptance.log')
                    time.sleep(.2)
            if browser is None:raise RuntimeError('candidate did not expose test endpoint')
            page=browser.contexts[0].pages[0]
            page.wait_for_function('window.api && document.querySelector("#app").__vue_app__')
            page.wait_for_function('document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.has("engine")')
            report['version']=page.evaluate("async()=> (await window.api.send('get_version')).data.version")
            page.evaluate("""async path=>{
                const s=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('engine');
                await s.openEpisode(path);
            }""",str(p))
            page.locator('[data-test=project-slim]').wait_for()
            assert not page.locator('[data-test=delete-sources]').is_checked()
            page.screenshot(path=str(evidence/'detail-full-960.png'))
            # Exercise the real renderer -> preload -> Python command flow,
            # with destructive effects confined to the generated fixture.
            page.locator('[data-test=delete-sources]').check()
            page.locator('[data-test=slim-preview]').click()
            page.locator('[data-test=confirm-source-removal]').wait_for()
            assert page.locator('[data-test=slim-execute]').is_disabled()
            page.locator('[data-test=confirm-source-removal]').check()
            page.locator('[data-test=slim-execute]').click()
            page.wait_for_function("document.querySelector('[data-test=project-slim] h3')?.textContent.includes('精简工程')")
            assert read_project(p)['mode']=='delivery'
            assert not raw.exists()
            assert protected()==before
            # A subsequent rating write and source regeneration guard use IPC.
            denied=page.evaluate("async path=>await window.api.send('regen_assets',{episode_dir:path})",str(p))
            assert denied['status']=='fail'
            assert '精简工程' in denied['errors'][0]['message']
            report['source_regeneration_blocked']=True
            report['protected_hashes_preserved']=len(before)
            report['compact_mode']='delivery'
            report['empty_source_remains_empty_after_refresh']=not raw.exists()
            page.screenshot(path=str(evidence/'detail-compact-960.png'))
            saved=page.evaluate("""async path=>await window.api.send('save_rating',{
                episode_dir:path,overall:92,note:'隔离测试评分',ratings:{'词1':{score:88,note:'人工原值'}}
            })""",str(p))
            assert saved['status']=='ok'
            rating=json.loads((p/'rating.json').read_text(encoding='utf-8'))
            assert rating['overall']==92 and rating['ratings']['词1']['score']==88
            report['rating_save_after_compaction']=True
            page.set_viewport_size(dict(width=800,height=600))
            page.screenshot(path=str(evidence/'detail-compact-800.png'))
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.set_viewport_size(dict(width=960,height=680))
            page.evaluate("""()=>{
                const s=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('engine');
                s.settingsTab='resource';s.phase='settings';
            }""")
            page.locator('[data-test=project-storage]').wait_for()
            page.screenshot(path=str(evidence/'storage-960.png'))
            report['horizontal_overflow']=page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert not report['horizontal_overflow']
            page.set_viewport_size(dict(width=800,height=600))
            page.screenshot(path=str(evidence/'storage-800.png'))
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            # A real second engine reads the existing compact project without
            # reconstructing a workspace. It does not acquire the running lock.
            report['workspace_created']=any(collection.rglob('.sticker-maker-workspaces'))
            assert not report['workspace_created']
            browser.close()
    finally:
        if proc.poll() is None:
            # This process and descendants belong only to this acceptance run.
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        log.close()
    cli=( [str(exe.parent/'resources/sticker-engine-cli/sticker-engine-cli.exe')] if args.app
          else [str(repo/'sticker_engine/.venv/Scripts/python.exe'),'-m','sticker_engine.cli'])
    response=subprocess.run(cli,env=env,input=json.dumps(dict(id='restart',cmd='list_episodes',args={}))+'\n',
                            cwd=repo/'sticker_engine',text=True,encoding='utf-8',capture_output=True,
                            timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert response.returncode==0,response.stderr
    messages=[json.loads(line) for line in response.stdout.splitlines() if line.strip().startswith('{')]
    result=next(m for m in messages if m.get('id')=='restart' and m.get('type')=='result')
    assert result['data']['episodes'][0]['project_mode']=='delivery'
    assert not raw.exists()
    report['restart_preserves_compact_mode']=True
    atomic_json(evidence/'electron-acceptance.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
