import pytest
from .test_fast_shelf import API, execute, harness
from sticker_engine.config.series import EpisodeMeta, save_meta, load_meta
from sticker_engine.publish.platform_data import sync_rows
from sticker_engine.library.runtime import LibraryRuntime


def test_failed_reservation_appears_in_fresh_shelfable_not_fresh_passed(tmp_path):
    p=tmp_path/'episode_failed'
    save_meta(p,EpisodeMeta(album_name='预约失败样本',platform_item_id='sid'))
    result=sync_rows(None,tmp_path,[{'Name':'预约失败样本','StikerID':'sid','Status':10}],lambda _:None,fetch_reasons=False)
    assert result['fresh_passed']==[]
    assert result.get('fresh_shelfable')==[str(p)]


def test_status10_can_reserve_once_using_original_id():
    api=API();api.status['sid']=10
    out=execute(api)
    assert out['status']==6 and out['item_id']=='sid'
    assert len(api.posts)==1 and api.posts[0][1]['params']['stikerid']=='sid'


def test_batch_includes_status10_but_dry_run_sends_nothing(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch)
    for p in h.eps:
        m=load_meta(p);m.platform_status='预约上架失败';save_meta(p,m)
    out=h.run(args={'dry_run':True})
    assert out.get('dry_run') is True and len(out['skipped_names'])==3
    assert not h.api.posts and not h.intents


def test_batch_status10_writes_once_and_persists_new_booking(tmp_path,monkeypatch):
    h=harness(tmp_path,monkeypatch)
    for p in h.eps:
        m=load_meta(p);m.platform_status='预约上架失败';save_meta(p,m)
    for n in range(3):h.api.status[f'sid{n}']=10
    out=h.run(args={'limit':1})
    assert out['published']==1 and len(h.api.posts)==1
    assert load_meta(h.eps[0]).platform_status=='已预约上架'
    assert h.finished==[('op-w0',True)]


def test_failed_reservation_placeholder_and_cached_rows_can_shelf(tmp_path):
    rt=LibraryRuntime(tmp_path);rt.bind('a@example.com',True)
    p=rt.placeholder({'StikerID':'sid','Name':'预约失败样本'})
    rt.rows()
    m=load_meta(p);m.platform_status='预约上架失败';m.published=True;save_meta(p,m)
    rt.commit_platform_metadata(p,m);rt.finish_platform_sync()
    assert rt.rows()[0]['can_shelf'] is True
    reopened=LibraryRuntime(tmp_path)
    assert reopened.rows()[0]['can_shelf'] is True


def test_failed_reservation_still_respects_conflict_gate(tmp_path):
    rt=LibraryRuntime(tmp_path);rt.bind('a@example.com',True)
    p=rt.placeholder({'StikerID':'sid','Name':'预约失败样本'})
    (p/'art.png').write_bytes(b'original')
    rt.capture(p)
    first=rt.works()[0]['revision']
    for name in ('branch a','branch b'):
        rt.library.write_revision(rt.account_id,first['work_id'],
            dict(first['metadata'],album_name=name),first['files'],parents=[first['revision_id']])
    assert rt.works()[0]['state']=='conflict'
    rt.rows();m=load_meta(p);m.platform_status='预约上架失败';save_meta(p,m)
    rt.commit_platform_metadata(p,m)
    rt.finish_platform_sync()
    assert rt.rows()[0]['can_shelf'] is False
