import pytest

from sticker_engine.config.series import load_meta, save_meta
from sticker_engine.library.runtime import LibraryRuntime


def fixture(tmp_path):
    rt = LibraryRuntime(tmp_path)
    rt.bind('a@example.com', True)
    path = rt.placeholder({'StikerID': '1', 'Name': 'original'})
    (path / 'art.png').write_bytes(b'original image')
    rt.capture(path)
    return rt, path


def test_platform_commit_does_not_hash_artwork_or_replace_other_metadata(tmp_path, monkeypatch):
    rt, path = fixture(tmp_path)
    old = rt.works()[0]['revision']
    monkeypatch.setattr(rt.library, 'put_file', lambda *a: pytest.fail('no artwork hashing'))
    meta = load_meta(path)
    meta.album_name = 'unsaved local rename'
    meta.platform_status = '审核通过'
    save_meta(path, meta)
    rt.commit_platform_metadata(path, meta)
    current = rt.works()[0]['revision']
    assert current['files'] == old['files']
    assert current['metadata']['album_name'] == 'original'
    assert current['metadata']['platform_status'] == '审核通过'
    assert current['parents'] == [old['revision_id']]
    assert load_meta(path).album_name == 'unsaved local rename'
    assert rt.rows()[0]['platform_status'] == '审核通过'


def test_changed_shared_head_is_not_silently_overwritten(tmp_path):
    rt, path = fixture(tmp_path)
    old = rt.works()[0]['revision']
    rt.library.write_revision(rt.account_id, old['work_id'],
        dict(old['metadata'], album_name='remote'), old['files'], parents=[old['revision_id']])
    meta = load_meta(path)
    meta.platform_status = '审核通过'
    with pytest.raises(ValueError, match='版本已变更'):
        rt.commit_platform_metadata(path, meta)
    assert rt.works()[0]['revision']['metadata']['album_name'] == 'remote'


def test_shelf_commit_replaces_stale_approved_observation_and_row(tmp_path):
    rt,path=fixture(tmp_path)
    meta=load_meta(path)
    meta.platform_status='审核通过';meta.platform_updated_at='2026-10-14 16:18:08'
    save_meta(path,meta);rt.commit_platform_metadata(path,meta);rt.finish_platform_sync()
    rows=rt.rows()
    rt.state.setdefault('platform_observations',{})[rt.account_id+'/'+meta.work_id]={
        'platform_item_id':meta.platform_item_id,'platform_status':'审核通过',
        'platform_updated_at':meta.platform_updated_at}
    # A shelf result changes only platform observations, not authored artwork.
    meta.platform_status='已预约上架';save_meta(path,meta)
    rt.commit_platform_metadata(path,meta);rt.finish_platform_sync()
    assert rt.rows()[0]['platform_status']=='已预约上架'
    assert rt.rows()[0]['can_shelf'] is False
    assert rt.works()[0]['revision']['metadata']['platform_status']=='已预约上架'
    assert rt.account_id+'/'+meta.work_id not in rt.state['platform_observations']


def test_later_capture_still_detects_local_artwork_edits(tmp_path):
    rt, path = fixture(tmp_path)
    old_files = rt.works()[0]['revision']['files']
    (path / 'art.png').write_bytes(b'changed locally')
    meta = load_meta(path)
    meta.platform_status = '审核通过'
    save_meta(path, meta)
    rt.commit_platform_metadata(path, meta)
    assert rt.works()[0]['revision']['files'] == old_files
    rt.capture(path)
    assert rt.works()[0]['revision']['files'] != old_files
    assert rt.works()[0]['state'] == 'available'


def test_foreign_account_cannot_commit(tmp_path):
    rt, path = fixture(tmp_path)
    meta = load_meta(path)
    meta.account_id = 'other'
    with pytest.raises(ValueError, match='账号'):
        rt.commit_platform_metadata(path, meta)


def test_new_platform_placeholder_is_committed_without_full_library_capture(tmp_path, monkeypatch):
    from sticker_engine.publish.platform_data import sync_rows
    rt = LibraryRuntime(tmp_path)
    rt.bind('a@example.com', True)
    monkeypatch.setattr(rt, 'capture_all', lambda: pytest.fail('no full scan'))
    result = sync_rows(None, rt.output_root,
        [{'StikerID': 'new', 'Name': 'new work', 'Status': 5}], lambda _: None,
        fetch_reasons=False, account_id=rt.account_id, placeholder_factory=rt.placeholder,
        on_meta_saved=rt.commit_platform_metadata)
    assert result['created'] == 1 and result['complete']
    assert result['persistence_failures'] == []
    assert rt.rows()[0]['platform_status'] == '审核通过'


def test_same_work_projection_does_not_restore_old_platform_status(tmp_path):
    import shutil
    rt, path = fixture(tmp_path)
    sibling = path.with_name('episode_sibling')
    shutil.copytree(path, sibling)
    rt.state['paths'][str(sibling)] = dict(rt.state['paths'][str(path)])
    sm = load_meta(sibling)
    sm.album_name = 'offline local rename'
    save_meta(sibling, sm)
    m = load_meta(path)
    m.platform_status = '审核通过'
    save_meta(path, m)
    rt.commit_platform_metadata(path, m)
    assert load_meta(sibling).platform_status == '审核通过'
    assert load_meta(sibling).album_name == 'offline local rename'
    assert rt.state['paths'][str(sibling)]['revision_id'] == rt.state['paths'][str(path)]['revision_id']


def test_conflicted_artwork_accepts_local_platform_observation_without_merging(tmp_path, monkeypatch):
    rt, path = fixture(tmp_path)
    first = rt.works()[0]['revision']
    for name in ('branch a', 'branch b'):
        rt.library.write_revision(rt.account_id, first['work_id'],
            dict(first['metadata'], album_name=name), first['files'], parents=[first['revision_id']])
    before = rt.works()[0]
    assert before['state'] == 'conflict'
    cached = rt.rows()
    meta = load_meta(path)
    meta.platform_status = '审核通过'
    meta.platform_updated_at = '2026-10-13 22:00:00'
    save_meta(path, meta)
    rt.commit_platform_metadata(path, meta)
    rt.finish_platform_sync()
    after = rt.works()[0]
    assert after['heads'] == before['heads']  # no merged or rewritten asset head
    monkeypatch.setattr(rt, 'works', lambda: pytest.fail('cached rows must not rescan the catalog'))
    rows = rt.rows()
    assert rows[0]['platform_status'] == '审核通过'
    assert rows[0]['resource_state'] == 'conflict'
    assert rows[0]['can_shelf'] is False and rows[0]['can_publish'] is False
    reopened = LibraryRuntime(tmp_path)
    assert reopened.rows()[0]['platform_status'] == '审核通过'
    assert reopened.works()[0]['heads'] == before['heads']
    reopened.capture(path)
    assert reopened.works()[0]['heads'] == before['heads']  # observations do not create asset branches later
    assert load_meta(path).platform_status == '审核通过'


def test_metadata_finish_updates_cached_rows_without_rescan(tmp_path, monkeypatch):
    rt, path = fixture(tmp_path)
    rt.rows()
    meta = load_meta(path)
    meta.platform_status = '审核通过'
    save_meta(path, meta)
    rt.commit_platform_metadata(path, meta)
    rt.finish_platform_sync()
    monkeypatch.setattr(rt, 'works', lambda: pytest.fail('no full resource scan'))
    assert rt.rows()[0]['platform_status'] == '审核通过'


def test_only_check_time_changed_does_not_write_shared_revision(tmp_path):
    rt, path = fixture(tmp_path)
    before = rt.works()[0]['revision']
    meta = load_meta(path)
    meta.platform_updated_at = '2026-10-13 22:00:00'
    save_meta(path, meta)
    rt.commit_platform_metadata(path, meta)
    rt.finish_platform_sync()
    assert rt.works()[0]['revision'] == before
    rt.capture(path)
    assert rt.works()[0]['revision'] == before
    assert rt.rows()[0]['platform_updated_at'] == '2026-10-13 22:00:00'
