import copy
import json
from pathlib import Path
import pytest
from sticker_engine.publish.sticker_metrics import parse_report,save_snapshot,load_snapshots,sync_reports,_cache_path
from sticker_engine.publish.platform_data import PlatformDataError,LIST_URL

A='a'*32
B='b'*32
def sample():
    report={'base_resp':{'ret':0},'Summary':{'StikerID':'sid','SendNum':35,'DataTime':'10月24日'},'Report':[{'Md5':A,'SendNum':27,'DataTime':'10月24日'},{'Md5':B,'SendNum':0,'DataTime':'10月24日'}]}
    detail={'base_resp':{'ret':0},'StikerID':'sid','Status':7,'StikerJson':{'Item':[{'md5':A,'index':'01','meaning':{'Unit':[{'lang':'zh_cn','content':'笑死'}]}},{'md5':B,'index':'02','meaning':{}}]}}
    return report,detail
def parsed():return parse_report(*sample(),'sid','专辑','account',captured_at='2026-10-26T01:00:00+00:00')

def test_identity_join_zero_period_not_cumulative():
    s=parsed();assert s['items'][0]['meaning']=='笑死' and s['items'][1]['sends']==0
    assert s['matched_count']==2 and s['capture_date']=='2026-10-26'
    assert s['period_kind']=='platform_daily' and 'total_sends' not in s
    assert s['items'][0]['data_time']=='10月24日'

@pytest.mark.parametrize('bad',[None,-1,True,1.5,'1.5','-',float('nan'),9007199254740992])
def test_invalid_counts_rejected(bad):
    r,d=sample();r['Report'][0]['SendNum']=bad
    with pytest.raises(PlatformDataError):parse_report(r,d,'sid','name','a')

def test_wrong_identity_duplicate_missing_date_and_empty():
    r,d=sample();r['Summary']['StikerID']='wrong'
    with pytest.raises(PlatformDataError):parse_report(r,d,'sid','n','a')
    r,d=sample();r['Report'].append(r['Report'][0])
    with pytest.raises(PlatformDataError):parse_report(r,d,'sid','n','a')
    r,d=sample();r['Report'][0]['DataTime']=''
    with pytest.raises(PlatformDataError):parse_report(r,d,'sid','n','a')
    r,d=sample();r['Report']=[]
    with pytest.raises(PlatformDataError):parse_report(r,d,'sid','n','a')

def test_unknown_md5_not_mislabelled_and_sparse_not_zero_filled():
    r,d=sample();r['Report']=r['Report'][:1];r['Report'][0]['Md5']='c'*32
    s=parse_report(r,d,'sid','n','a');assert s['matched_count']==0 and len(s['items'])==1
    assert s['items'][0]['meaning']=='' and not s['items'][0]['matched']

def test_cache_account_identity_atomic_failure(tmp_path,monkeypatch):
    s=parsed();save_snapshot(tmp_path,'account',s);p=_cache_path(tmp_path,'account','sid');old=p.read_bytes()
    works=[{'platform_item_id':'sid'},{'platform_item_id':'sid'}]
    assert load_snapshots(tmp_path,'account',works)['cached_albums']==1
    assert load_snapshots(tmp_path,'other',works)['albums']==[]
    monkeypatch.setattr('sticker_engine.publish.sticker_metrics.os.replace',lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    s['items'][0]['sends']=30
    with pytest.raises(OSError):save_snapshot(tmp_path,'account',s)
    assert p.read_bytes()==old and not list(p.parent.glob('*.tmp'))

def test_corrupt_cache_preserved_and_flagged(tmp_path):
    p=_cache_path(tmp_path,'account','sid');p.parent.mkdir(parents=True);p.write_text('{broken','utf-8')
    r=load_snapshots(tmp_path,'account',[{'platform_item_id':'sid'}]);assert r['albums']==[] and len(r['cache_errors'])==1
    assert p.read_text('utf-8')=='{broken'

def fake_read(page,url):
    return {'base_resp':{'ret':0},'List':[{'StikerID':'sid','Name':'专辑','Status':7}]} if url==LIST_URL else sample()[0]

def test_sync_owned_list_only_cancel_and_failed_read_retains_old(tmp_path):
    works=[{'platform_item_id':'sid'}]
    with pytest.raises(ValueError):sync_reports(None,works,tmp_path,'a',item_ids=['other'],reader=fake_read)
    r=sync_reports(None,works,tmp_path,'a',should_stop=lambda:True,reader=lambda *a:pytest.fail('cancelled must not read'))
    assert r['cancelled'] and r['updated']==0
    r=sync_reports(None,works,tmp_path,'a',reader=fake_read,detail_reader=lambda *a:sample()[1]);assert r['updated']==1
    before=_cache_path(tmp_path,'a','sid').read_bytes()
    def bad_read(page,url):
        if url==LIST_URL:return fake_read(page,url)
        raise PlatformDataError('timeout')
    r=sync_reports(None,works,tmp_path,'a',reader=bad_read,detail_reader=lambda *a:sample()[1]);assert not r['complete'] and r['updated']==0
    assert _cache_path(tmp_path,'a','sid').read_bytes()==before

def test_account_changed_before_commit_does_not_save(tmp_path):
    calls=[]
    def guard():
        calls.append(1)
        if len(calls)>1:raise ValueError('account changed')
    r=sync_reports(None,[{'platform_item_id':'sid'}],tmp_path,'a',reader=fake_read,detail_reader=lambda *a:sample()[1],guard=guard)
    assert not r['complete'] and r['updated']==0 and not _cache_path(tmp_path,'a','sid').exists()

def test_unowned_or_removed_id_not_fetched(tmp_path):
    r=sync_reports(None,[{'platform_item_id':'sid'}],tmp_path,'a',item_ids=['sid'],reader=lambda *a:{'base_resp':{'ret':0},'List':[]},detail_reader=lambda *a:pytest.fail('must not read unowned detail'))
    assert r['updated']==0 and len(r['failures'])==1


def test_new_command_registered_for_cancel_before_library_preparation(monkeypatch):
    from sticker_engine import cli
    observed=[]
    def invoke(module,request_id,command,args,handler):
        observed.append(request_id in module._stop_events)
    monkeypatch.setattr('sticker_engine.library.hooks.invoke',invoke)
    monkeypatch.setattr(cli,'_log',lambda *args,**kwargs:None)
    cli._handle_in_thread('metrics-test','sync_sticker_metrics',{})
    assert observed==[True] and 'metrics-test' not in cli._stop_events


def test_current_binding_disk_change_is_detected(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from sticker_engine.publish.sticker_metrics import current_scope
    runtime=SimpleNamespace(account_id='a',require_account=lambda:None,rows=lambda:[{'platform_item_id':'sid'}])
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda engine:runtime)
    engine=SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path)))
    path=tmp_path/'resource_library/device.json';path.parent.mkdir();path.write_text('{"account_id":"a"}','utf-8')
    assert current_scope(engine)[0]=='a'
    path.write_text('{"account_id":"b"}','utf-8')
    with pytest.raises(ValueError,match='绑定已切换'):current_scope(engine)


def test_metrics_hooks_are_mutually_exclusive_and_do_not_capture_artwork():
    from sticker_engine.library.hooks import MUTATIONS,PLATFORM,LONG_TASKS,FAST_LOCAL
    assert 'sync_sticker_metrics' in MUTATIONS & PLATFORM & LONG_TASKS
    assert 'get_sticker_metrics' in FAST_LOCAL and 'get_sticker_metrics' not in MUTATIONS


def test_legacy_episode_list_exposes_exact_platform_identity(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from sticker_engine import cli
    from sticker_engine.config.series import EpisodeMeta,save_meta
    path=tmp_path/'episode_sample';path.mkdir()
    save_meta(path,EpisodeMeta(album_name='SAMPLE',platform_item_id='sid',platform_status='已上架'))
    monkeypatch.setattr(cli,'_ensure_engine',lambda:SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(output_root=tmp_path))))
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda engine:None)
    out=[];monkeypatch.setattr(cli,'_result',lambda request,status,**kwargs:out.append(kwargs['data']))
    cli.cmd_list_episodes('sample',{})
    assert out[0]['episodes'][0]['platform_item_id']=='sid'
