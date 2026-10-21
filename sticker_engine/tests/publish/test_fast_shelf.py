"""Real request contract, no replay, cancellation, and exact status persistence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
import threading

import pytest
from sticker_engine.publish.fast_shelf import (
    reserve_today, ShelfCancelled, ShelfNotEligible, ShelfOutcomeUnknown)
from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta

DAY='2026-10-14'

class Response:
    ok=True
    def __init__(self, body):self.body=body;self.disposed=False
    def json(self):return self.body
    def dispose(self):self.disposed=True

class API:
    def __init__(self):
        self.status={};self.calls=[];self.posts=[];self.ret=0;self.accept=True
        self.timeout=False;self.bad_json=False;self.day=DAY;self.on_post=lambda:None
    def get(self,url,**kw):
        from urllib.parse import parse_qs,urlparse
        sid=parse_qs(urlparse(url).query)['stikerid'][0]
        self.calls.append(sid)
        return Response({'base_resp':{'ret':0},'StikerID':sid,'Status':self.status.get(sid,5),'OpenTime':self.day})
    def post(self,url,**kw):
        self.posts.append((url,kw));sid=kw['params']['stikerid']
        if self.accept:self.status[sid]=6
        self.on_post()
        if self.timeout:raise TimeoutError('response lost')
        if self.bad_json:
            r=Response(None);r.json=Mock(side_effect=ValueError('bad json'));return r
        return Response({'base_resp':{'ret':self.ret}})

def execute(api,**kwargs):
    page=NS(context=NS(request=api))
    return reserve_today(page,'sid',now=datetime(2026,10,14,12,34,56),sleep=lambda _:None,**kwargs)

def test_fast_contract_has_one_post_and_no_page_navigation():
    api=API();before=Mock();out=execute(api,before_write=before)
    assert out['status']==6 and out['status_text']=='已预约上架'
    assert len(api.posts)==1 and before.call_count==1
    url,args=api.posts[0]
    assert url.endswith('/cgi-bin/mmemoticon-bin/stikeroper')
    assert args['params']=={'stikerid':'sid','opentime':'2026-10-14 12:34:56','oper':'open'}
    assert args['max_retries']==0 and args['timeout']==15000
    assert len(api.calls)==2

@pytest.mark.parametrize('kind',['timeout','bad_json','nonzero'])
def test_lost_or_error_response_is_reconciled_without_replay(kind):
    api=API();api.timeout=kind=='timeout';api.bad_json=kind=='bad_json'
    if kind=='nonzero':api.ret=-10
    assert execute(api)['status']==6
    assert len(api.posts)==1

@pytest.mark.parametrize('ret',[0,-10])
def test_ret_or_http_success_without_platform_booking_is_unknown(ret):
    api=API();api.ret=ret;api.accept=False
    with pytest.raises(ShelfOutcomeUnknown):execute(api)
    assert len(api.posts)==1

def test_wrong_reservation_date_is_not_counted_as_success():
    api=API();api.day='2026-10-15'
    with pytest.raises(ShelfOutcomeUnknown):execute(api)
    assert len(api.posts)==1

@pytest.mark.parametrize('state',[2,6,7,9,11])
def test_fresh_nonapproved_status_never_sends(state):
    api=API();api.status['sid']=state;before=Mock()
    with pytest.raises(ShelfNotEligible):execute(api,before_write=before)
    assert not api.posts and not before.called


def test_failed_reservation_after_post_is_not_success_and_never_replayed():
    api = API()
    api.on_post = lambda: api.status.update(sid=10)
    with pytest.raises(ShelfOutcomeUnknown):
        execute(api)
    assert len(api.posts) == 1

def test_cancel_before_send_has_no_intent_or_request():
    api=API();before=Mock()
    with pytest.raises(ShelfCancelled):execute(api,should_stop=lambda:True,before_write=before)
    assert not api.posts and not before.called

def test_cancel_after_preflight_has_no_intent_or_request():
    api=API();checks=iter([False,True]);before=Mock()
    with pytest.raises(ShelfCancelled):execute(api,should_stop=lambda:next(checks),before_write=before)
    assert not api.posts and not before.called

def test_cancel_after_post_still_verifies_current_item():
    api=API();stop=threading.Event();api.on_post=stop.set
    assert execute(api,should_stop=stop.is_set)['status']==6
    assert len(api.calls)==2 and stop.is_set()

def test_intent_failure_never_sends():
    api=API()
    with pytest.raises(ValueError):execute(api,before_write=Mock(side_effect=ValueError('pending operation')))
    assert not api.posts

def harness(tmp_path,monkeypatch,api=None,runtime=True):
    import sticker_engine.cli as cli
    import sticker_engine.publish.browser as browser
    import sticker_engine.library.hooks as hooks
    import sticker_engine.library.operations as operations
    import playwright.sync_api as pw
    api=api or API();api.day=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    eps=[]
    for n in range(3):
        path=tmp_path/f'episode_{n}'
        save_meta(path,EpisodeMeta(album_name=f'作品{n}',work_id=f'w{n}',account_id='account',
                                  platform_item_id=f'sid{n}',platform_status='审核通过'))
        eps.append(path)
    engine=NS(config=NS(paths=NS(output_root=tmp_path)))
    rt=NS(account_id='account',rows=lambda:[{'work_id':f'w{n}','can_shelf':True} for n in range(3)],
          commit_platform_metadata=Mock(),finish_platform_sync=Mock())
    monkeypatch.setattr(cli,'_ensure_engine',lambda:engine)
    monkeypatch.setattr(hooks,'runtime_for',lambda _:rt if runtime else None)
    intents=[];finished=[]
    def begin(_,work_id,*a):intents.append(work_id);return 'op-'+work_id
    monkeypatch.setattr(operations,'begin',begin)
    monkeypatch.setattr(operations,'finish',lambda _,op,success:finished.append((op,success)))
    class Session:
        def start(self,**kw):return NS(context=NS(request=api))
        def ensure_login(self,*a,**kw):return True
        def close(self):pass
    class Context:
        def __enter__(self):return None
        def __exit__(self,*a):pass
    monkeypatch.setattr(browser,'BrowserSession',lambda *a,**kw:Session())
    monkeypatch.setattr(pw,'sync_playwright',Context)
    sync=lambda *a,**kw:{'list_complete':True,'fresh_passed':[str(p) for p in eps]}
    results=[]
    def run(stop=None,args=None):
        cli._run_shelf_passed('fast-test',args or {},tmp_path,sync,lambda _:None,stop=stop,
                              result_callback=lambda *a,**kw:results.append(kw['data']))
        return results[-1]
    return NS(run=run,eps=eps,api=api,intents=intents,finished=finished,rt=rt,cli=cli)

def test_command_uses_api_persists_booked_and_cancels_remaining(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch);stop=threading.Event()
    h.api.on_post=lambda:stop.set() if len(h.api.posts)==2 else None
    out=h.run(stop)
    assert out['source']=='api' and out['published']==2 and out['cancelled']
    assert out['remaining']==['作品2'] and not out['failed']
    assert load_meta(h.eps[1]).platform_status=='已预约上架'
    assert load_meta(h.eps[2]).platform_status=='审核通过'
    assert h.finished==[('op-w0',True),('op-w1',True)]
    assert h.rt.commit_platform_metadata.call_count==2 and h.rt.finish_platform_sync.call_count==2

def test_command_unknown_stops_batch_and_keeps_unresolved_intent(tmp_path,monkeypatch):
    api=API();api.accept=False;api.timeout=True
    h=harness(tmp_path,monkeypatch,api)
    out=h.run()
    assert out['published']==0 and len(out['failed'])==1
    assert len(api.posts)==1 and len(out['remaining'])==2
    assert h.finished==[('op-w0',False)]

def test_command_dry_run_never_starts_browser_or_intent(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch);out=h.run(args={'dry_run':True})
    assert out['dry_run'] and not h.api.posts and not h.intents

def test_command_account_gate_skips_foreign_items(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch);h.rt.account_id='other'
    assert h.run()['published']==0 and not h.api.posts

def test_command_deduplicates_dual_projection_identity(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch,runtime=False)
    meta=load_meta(h.eps[1]);meta.platform_item_id='sid0';save_meta(h.eps[1],meta)
    assert h.run()['published']==2 and len(h.api.posts)==2

def test_command_local_save_failure_retains_confirmed_platform_success(tmp_path,monkeypatch):
    import sticker_engine.config.series as series
    h=harness(tmp_path,monkeypatch);original=series.save_meta
    def save(path,meta):
        if meta.platform_status=='已预约上架':raise OSError('disk full')
        return original(path,meta)
    monkeypatch.setattr(series,'save_meta',save)
    out=h.run(args={'limit':1})
    assert out['published']==1 and not out['failed'] and len(out['warnings'])==1
    assert h.finished==[('op-w0',True)]
