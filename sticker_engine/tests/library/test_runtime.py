import json
from pathlib import Path

import pytest

from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta


def runtime(tmp_path):
    from sticker_engine.library.runtime import LibraryRuntime
    return LibraryRuntime(tmp_path)


def legacy(tmp_path, name='episode_old'):
    path = tmp_path / 'episodes' / name
    save_meta(path, EpisodeMeta(album_name='测试作品', platform_item_id='platform_1'))
    (path / '原图').mkdir()
    (path / '原图/grid.png').write_bytes(b'raw')
    (path / '最终版').mkdir()
    (path / '最终版/开心.png').write_bytes(b'final')
    return path


def test_binding_requires_legacy_confirmation_and_retains_identity(tmp_path):
    old = legacy(tmp_path)
    rt = runtime(tmp_path)
    with pytest.raises(ValueError, match='确认'):
        rt.bind('first@example.com')
    rt.bind('first@example.com', confirm_legacy=True)
    assert load_meta(old).account_id == rt.account_id
    work_id = load_meta(old).work_id
    rt.capture(old)
    assert len(rt.works()) == 1
    assert rt.works()[0]['work_id'] == work_id


def test_placeholder_capture_hydrates_without_duplicate(tmp_path):
    rt = runtime(tmp_path); rt.bind('a@example.com', True)
    path = rt.placeholder({'StikerID': 'platform_1', 'Name': '测试作品'})
    rt.capture(path)
    assert rt.works()[0]['state'] == 'placeholder'
    (path / '原图').mkdir(); (path / '原图/raw.png').write_bytes(b'raw')
    rt.capture(path)
    assert len(rt.works()) == 1
    assert rt.works()[0]['state'] == 'available'


def test_account_switch_does_not_reassign_existing_work(tmp_path):
    rt = runtime(tmp_path); rt.bind('a@example.com', True)
    a = rt.placeholder({'StikerID': 'same', 'Name': '同名'})
    rt.capture(a)
    original = load_meta(a).account_id
    rt.bind('b@example.com', True)
    b = rt.placeholder({'StikerID': 'same', 'Name': '同名'})
    rt.capture(b)
    assert a != b
    assert load_meta(a).account_id == original
    assert len(rt.works()) == 1
    with pytest.raises(ValueError, match='账号'):
        rt.capture(a)


def test_connect_restart_refresh_and_local_hide(tmp_path):
    a = runtime(tmp_path / 'a'); a.bind('a@example.com', True)
    p = a.placeholder({'StikerID': '1', 'Name': '作品'})
    a.capture(p)
    shared = tmp_path / 'shared'
    from sticker_engine.library.catalog import ResourceLibrary
    ResourceLibrary(shared, create=True).merge_from(a.library)
    b = runtime(tmp_path / 'b'); b.bind('a@example.com', True); b.connect(shared)
    wid = b.works()[0]['work_id']
    fresh = runtime(tmp_path / 'b')
    assert fresh.status()['root'] == str(shared.resolve())
    assert fresh.rows()[0]['work_id'] == wid
    fresh.delete(wid, 'hide')
    assert fresh.rows() == []
    assert a.rows()


def test_capture_is_idempotent_and_conflict_not_silently_overwritten(tmp_path):
    rt = runtime(tmp_path); rt.bind('a@example.com', True)
    p = rt.placeholder({'StikerID': '1', 'Name': '作品'})
    first = rt.capture(p)
    assert rt.capture(p)['revision_id'] == first['revision_id']
    wid = first['work_id']
    rt.library.write_revision(rt.account_id, wid, {'album_name': '远端'}, {}, parents=[first['revision_id']])
    meta = load_meta(p); meta.album_name = '本地'; save_meta(p, meta)
    rt.capture(p)
    assert rt.library.read_work(rt.account_id, wid)['state'] == 'conflict'
    assert rt.rows()[0]['can_publish'] is False


def test_external_custom_path_collected_as_portable_resource(tmp_path):
    old = legacy(tmp_path)
    custom = tmp_path / 'my-banner.png'; custom.write_bytes(b'banner')
    m = load_meta(old); m.banner_custom = str(custom); save_meta(old, m)
    rt = runtime(tmp_path); rt.bind('a@example.com', True)
    rt.capture(old)
    revision = rt.works()[0]['revision']
    assert not Path(revision['metadata']['banner_custom']).is_absolute()
    assert revision['metadata']['banner_custom'] in revision['files']


def test_missing_shared_root_does_not_recreate_library(tmp_path):
    rt = runtime(tmp_path / 'state'); rt.bind('a@example.com', True)
    from sticker_engine.library.catalog import ResourceLibrary
    shared = tmp_path / 'shared'; ResourceLibrary(shared, create=True)
    rt.connect(shared)
    shared.rename(tmp_path / 'offline')
    offline = runtime(tmp_path / 'state').refresh()
    assert offline['offline'] is True
    assert offline['root'] == str(shared)
    assert not shared.exists()


def test_unpublished_generated_work_keeps_single_identity_and_original_path(tmp_path):
    rt = runtime(tmp_path); rt.bind('a@example.com', True)
    path = rt.output_root / 'episode_new'
    save_meta(path, EpisodeMeta(album_name='新草稿'))
    (path / 'raw.png').write_bytes(b'raw')
    rt.capture(path); rt.refresh(); rt.refresh()
    assert len(rt.works()) == 1
    assert len(list(rt.output_root.glob('episode*'))) == 1
    rev = rt.works()[0]['revision']
    assert rev['metadata']['work_id'] == load_meta(path).work_id == rev['work_id']
    assert rt.rows()[0]['path'] == str(path)
