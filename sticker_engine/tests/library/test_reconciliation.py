import copy
import json

import pytest

from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.library.reconciliation import propose, repair


def setup(tmp_path, change=None):
    lib=ResourceLibrary(tmp_path/'lib', create=True)
    p=tmp_path/'image.png';p.write_bytes(b'original-artwork')
    files={'最终版/开心.png':lib.put_file(p)}
    meta={'album_name':'作品', 'platform_item_id':'platform-1', 'platform_updated_at':'2026-10-01 00:00:00', 'platform_sends':'1'}
    root=lib.write_revision('account','work',meta,files,parents=[])
    a=lib.write_revision('account','work',dict(meta,platform_updated_at='2026-10-02 00:00:00',platform_sends='2'),files,parents=[root['revision_id']])
    second=dict(meta,platform_updated_at='2026-10-03 00:00:00',platform_sends='3')
    if change:second.update(change)
    b=lib.write_revision('account','work',second,files,parents=[root['revision_id']])
    return lib,root,a,b


def test_metadata_only_merge_preserves_artwork_and_history(tmp_path):
    lib,root,a,b=setup(tmp_path)
    before={r['revision_id']:r for r in lib.revisions('account','work')}
    result=repair(lib,'account','work')
    assert result['merged'] and result['state']=='available'
    work=lib.read_work('account','work')
    assert work['revision']['files']==a['files']
    assert work['revision']['metadata']['platform_sends']=='3'
    assert set(work['revision']['parents'])=={a['revision_id'],b['revision_id']}
    assert all(r==before[r['revision_id']] for r in lib.revisions('account','work') if r['revision_id'] in before)
    assert not repair(lib,'account','work')['merged']


@pytest.mark.parametrize('change',[{'album_name':'不同作品'},{'platform_item_id':'other'},{'cover_pick':2}])
def test_authored_metadata_or_identity_divergence_stays_conflicted(tmp_path,change):
    lib,*_=setup(tmp_path,change)
    assert not repair(lib,'account','work')['merged']
    assert lib.read_work('account','work')['state']=='conflict'


def test_material_difference_never_auto_chosen(tmp_path):
    lib,root,a,b=setup(tmp_path)
    p=tmp_path/'other.png';p.write_bytes(b'changed-artwork')
    lib.write_revision('account','work',a['metadata'],{'最终版/开心.png':lib.put_file(p)},parents=[a['revision_id']])
    assert not repair(lib,'account','work')['merged']


def with_ratings(tmp_path, left,right):
    lib,root,a,b=setup(tmp_path)
    for index,(head,data) in enumerate(((a,left),(b,right))):
        p=tmp_path/f'rating{index}.json';p.write_text(json.dumps(data),encoding='utf-8')
        lib.write_revision('account','work',head['metadata'],dict(head['files'],**{'rating.json':lib.put_file(p)}),parents=[head['revision_id']])
    return lib


def test_disjoint_ratings_union_and_preserve_all_scores(tmp_path):
    lib=with_ratings(tmp_path,{'overall':4,'ratings':{'开心':{'score':5,'note':'不错'}}},
                    {'overall':4,'ratings':{'晚安':{'score':3,'note':'字糊'}}})
    assert repair(lib,'account','work')['merged']
    ref=lib.read_work('account','work')['revision']['files']['rating.json'];d=ref['sha256']
    data=json.loads((lib.root/'objects'/d[:2]/d).read_text(encoding='utf-8'))
    assert data['ratings']=={'开心':{'score':5,'note':'不错'},'晚安':{'score':3,'note':'字糊'}}


def test_overlapping_different_score_not_overwritten(tmp_path):
    lib=with_ratings(tmp_path,{'ratings':{'开心':{'score':5}}},{'ratings':{'开心':{'score':2}}})
    assert not repair(lib,'account','work')['merged']


def test_stale_expected_heads_refused(tmp_path):
    lib,root,a,b=setup(tmp_path)
    assert not repair(lib,'account','work',[a['revision_id']])['merged']


def test_same_timestamp_contradiction_not_last_writer_wins(tmp_path):
    lib,root,a,b=setup(tmp_path,{'platform_updated_at':'2026-10-02 00:00:00'})
    assert not repair(lib,'account','work')['merged']


def test_local_old_observation_does_not_fork_new_platform_snapshot(tmp_path):
    from sticker_engine.library.runtime import LibraryRuntime
    from sticker_engine.config.series import EpisodeMeta,load_meta,save_meta
    rt=LibraryRuntime(tmp_path/'device');rt.bind('a@example.com',True)
    p=rt.output_root/'episode_old'
    save_meta(p,EpisodeMeta(album_name='作品',platform_item_id='1',platform_sends='1'))
    (p/'art.png').write_bytes(b'art')
    initial=rt.capture(p)
    head=rt.library.read_work(rt.account_id,initial['work_id'])['revision']
    remote=rt.library.write_revision(rt.account_id,initial['work_id'],dict(head['metadata'],platform_sends='9',platform_updated_at='2026-10-14 01:00:00'),head['files'],parents=[head['revision_id']])
    meta=load_meta(p);meta.platform_sends='3';save_meta(p,meta)
    rt.capture(p)
    work=rt.library.read_work(rt.account_id,initial['work_id'])
    assert work['state']=='available' and work['revision']['revision_id']==remote['revision_id']
    assert len(rt.library.revisions(rt.account_id,initial['work_id']))==2
