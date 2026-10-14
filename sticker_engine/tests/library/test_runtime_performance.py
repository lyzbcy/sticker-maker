import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from sticker_engine.library import runtime as mod
from sticker_engine.library.runtime import LibraryRuntime, runtime_for_user_data, active_runtime, write_json
from sticker_engine.library.hooks import runtime_for
from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.config.series import EpisodeMeta, save_meta, load_meta


def test_engine_publisher_and_registry_share_one_instance(tmp_path, monkeypatch):
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    one = runtime_for_user_data(tmp_path)
    one.bind('fixture@example.com', True)
    engines = [SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path))) for _ in range(2)]
    assert runtime_for(engines[0]) is one
    assert runtime_for(engines[1]) is one
    assert active_runtime() is one
    one.state['marker_from_publisher'] = {'revision_id': 'fresh'}
    assert runtime_for(engines[0]).state['marker_from_publisher']['revision_id'] == 'fresh'


def test_disabled_registry_becomes_enabled_without_replacing_actor(tmp_path, monkeypatch):
    from sticker_engine.library.commands import dispatch
    engine = SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path)))
    cli = SimpleNamespace(_ensure_engine=lambda: engine, _engine=engine)
    assert runtime_for(engine) is None
    original = runtime_for_user_data(tmp_path)
    dispatch(cli, 'bind_account', 'test', {'account': 'fixture@example.com', 'confirm_legacy': True})
    assert runtime_for(engine) is original and original.enabled


def test_registry_creation_is_thread_safe_and_paths_are_canonical(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        actors = list(pool.map(lambda _: runtime_for_user_data(tmp_path / 'child' / '..'), range(20)))
    assert all(a is actors[0] for a in actors)
    assert actors[0] is runtime_for_user_data(tmp_path)
    assert actors[0] is not runtime_for_user_data(tmp_path / 'other')


def test_account_switch_does_not_reuse_previous_row_snapshot(tmp_path):
    rt = runtime_for_user_data(tmp_path);rt.bind('first@example.com', True)
    rt.state['last_rows'] = [{'work_id': 'old-account-item', 'path': 'old'}]
    rt._rows_at = __import__('time').monotonic()
    rt.bind('second@example.com', True)
    assert rt.rows() == []
    assert rt.account_id == mod.account_key('second@example.com')


def test_compact_write_keeps_all_values_and_fsync_before_replace(tmp_path, monkeypatch):
    path = tmp_path / 'state.json';path.write_text('{"old":true}', encoding='utf-8')
    value = {'中文': ['初始', None, True, 1.25], 'nested': {'a': 2}}
    events = [];replace = mod.os.replace;fsync = mod.os.fsync
    def sync(fd):
        events.append('fsync');fsync(fd)
    def swap(src, dst):
        assert path.read_text(encoding='utf-8') == '{"old":true}'
        assert json.loads(Path(src).read_text(encoding='utf-8')) == value
        events.append('replace');replace(src, dst)
    monkeypatch.setattr(mod.os, 'fsync', sync);monkeypatch.setattr(mod.os, 'replace', swap)
    write_json(path, value)
    assert events == ['fsync', 'replace']
    assert json.loads(path.read_text(encoding='utf-8')) == value
    assert '\n' not in path.read_text(encoding='utf-8')


def test_failed_serialization_keeps_old_file_and_cleans_temp(tmp_path):
    path = tmp_path / 'state.json';path.write_text('{"old":true}', encoding='utf-8')
    with pytest.raises(TypeError):write_json(path, {'bad': object()})
    assert path.read_text(encoding='utf-8') == '{"old":true}'
    assert list(tmp_path.glob('*.tmp')) == []


def test_clean_cache_is_not_rewritten_but_missing_cache_is_rebuilt(tmp_path):
    lib = ResourceLibrary(tmp_path / 'lib', create=True)
    p = tmp_path / 'a.txt';p.write_text('original')
    ref = lib.put_file(p);lib.write_revision('a', 'w', {'kind': 'episode'}, {'a.txt': ref})
    lib.list_works('a');cache = lib._disk_cache_path();before = cache.stat().st_mtime_ns
    lib.list_works('a');assert cache.stat().st_mtime_ns == before
    cache.unlink();lib.save_disk_cache();assert cache.is_file()


def test_dirty_cache_still_persists_new_head_and_returns_deep_copy(tmp_path):
    lib = ResourceLibrary(tmp_path / 'lib', create=True)
    p = tmp_path / 'a.txt';p.write_text('original');ref = lib.put_file(p)
    r1 = lib.write_revision('a', 'w', {'value': 1}, {'a.txt': ref});lib.list_works('a')
    r2 = lib.write_revision('a', 'w', {'value': 2}, {'a.txt': ref}, parents=[r1['revision_id']])
    rows = lib.list_works('a');rows[0]['revision']['metadata']['value'] = 99
    assert ResourceLibrary(tmp_path / 'lib').read_work('a', 'w')['revision']['revision_id'] == r2['revision_id']
    assert lib.read_work('a', 'w')['revision']['metadata']['value'] == 2


def fixture(tmp_path, monkeypatch):
    rt = LibraryRuntime(tmp_path);rt.bind('fixture@example.com', True)
    ep = rt.output_root / 'episode_test';ep.mkdir(parents=True)
    save_meta(ep, EpisodeMeta(work_id='fixed', account_id=rt.account_id, album_name='original'))
    (ep / 'art.txt').write_text('original')
    calls = []
    monkeypatch.setattr(rt, 'capture', lambda path: calls.append(Path(path)))
    rt.capture_all();calls.clear()
    return rt, ep, calls


def test_only_observation_changes_do_not_rehash_material(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    meta = load_meta(ep);meta.platform_updated_at = 'new';meta.platform_status = '审核通过';save_meta(ep, meta)
    rt.capture_all();assert calls == []


@pytest.mark.parametrize('field,value', [('album_name', 'renamed'), ('platform_item_id', 'platform-new')])
def test_authored_or_identity_change_still_forces_capture(tmp_path, monkeypatch, field, value):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    meta = load_meta(ep);setattr(meta, field, value);save_meta(ep, meta)
    rt.capture_all();assert calls == [ep]


def test_nested_relative_paths_are_part_of_light_snapshot(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    (ep / 'one').mkdir();(ep / 'one' / 'same.txt').write_text('value')
    rt.capture_all();calls.clear()
    (ep / 'one').rename(ep / 'two')
    rt.capture_all();assert calls == [ep]


def test_external_asset_update_forces_capture(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    external = tmp_path / 'external.png';external.write_bytes(b'first')
    meta = load_meta(ep);meta.cover_custom = str(external);save_meta(ep, meta)
    rt.capture_all();calls.clear();external.write_bytes(b'longer updated artwork')
    rt.capture_all();assert calls == [ep]


def test_other_account_and_non_directory_are_skipped_without_unpack_error(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    foreign = rt.output_root / 'episode_foreign';save_meta(foreign, EpisodeMeta(account_id='different'))
    (rt.output_root / 'episode_file').write_text('not a folder')
    rt.capture_all();assert calls == []


def test_capture_progress_is_observable_and_callback_failures_do_not_stop_work(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    events = [];rt._progress_callback = events.append;rt.capture_all()
    assert events[0]['phase'] == 'capture_scan' and events[-1]['completed'] == events[-1]['total'] == 1
    rt._progress_callback = lambda event: (_ for _ in ()).throw(RuntimeError('listener failed'))
    rt.capture_all();assert calls == []


def test_nested_meta_json_is_a_material_file(tmp_path, monkeypatch):
    rt, ep, calls = fixture(tmp_path, monkeypatch)
    (ep / 'nested').mkdir();file = ep / 'nested' / 'meta.json';file.write_text('{"value":1}')
    rt.capture_all();calls.clear();file.write_text('{"value":222}')
    rt.capture_all();assert calls == [ep]


def test_hook_restores_progress_callback_on_failure(tmp_path, monkeypatch):
    from sticker_engine.library import hooks
    rt = runtime_for_user_data(tmp_path);rt.bind('fixture@example.com', True)
    engine = SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path)))
    previous = lambda event: None;rt._progress_callback = previous
    monkeypatch.setattr(rt, 'refresh', lambda **kw: {})
    cli = SimpleNamespace(_ensure_engine=lambda: engine, _emit=Mock(), _result=Mock(), _engine=engine)
    def handler(req, args):
        assert rt._progress_callback is not previous
        raise RuntimeError('original task failed')
    with pytest.raises(RuntimeError):hooks.invoke(cli, 'request', 'run', {}, handler)
    assert rt._progress_callback is previous
