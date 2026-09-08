import json
from pathlib import Path

from sticker_engine import cli


def test_library_commands_registered():
    required = {'library_status', 'library_bind_account', 'library_preview',
                'library_execute', 'library_connect', 'library_import',
                'library_refresh', 'library_resolve', 'library_delete',
                'library_handoff', 'library_capture'}
    assert required <= cli.HANDLERS.keys()


def test_bound_output_path_survives_resolve(tmp_path, monkeypatch):
    from sticker_engine.config.paths import resolve_paths
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    state = tmp_path / 'resource_library/device.json'
    state.parent.mkdir()
    state.write_text(json.dumps({'account_id': 'a', 'library_id': 'lib',
                                 'root': str(tmp_path / 'shared')}))
    assert resolve_paths('darwin').output_root == tmp_path / 'resource_library/workspaces/lib/a/episodes'
    assert resolve_paths('darwin').prefs_file == tmp_path / 'resource_library/workspaces/lib/a/settings/prefs.yaml'


def test_real_command_migration_restart_and_second_device(tmp_path, monkeypatch):
    from sticker_engine.config.series import save_meta, EpisodeMeta
    state = tmp_path / 'device_a'
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(state))
    monkeypatch.setattr(cli, '_engine', None)
    events = []
    monkeypatch.setattr(cli, '_emit', events.append)
    def call(cmd, **args):
        events.clear()
        cli._handle_in_thread('test', cmd, args)
        results = [x for x in events if x.get('type') in ('result', 'error')]
        assert results and results[-1].get('status') == 'ok', results
        return results[-1].get('data')
    source = state / 'episodes/episode_original'
    save_meta(source, EpisodeMeta(album_name='可迁移作品'))
    (source / '原图').mkdir(); (source / '原图/grid.png').write_bytes(b'raw')
    call('library_bind_account', account='a@example.com', confirm_legacy=True)
    target = tmp_path / '共享库'
    plan = call('library_preview', target=str(target), mode='migration', cleanup=True)
    result = call('library_execute', plan_id=plan['plan_id'])
    assert result['state'] == 'completed', result
    assert not (source / '原图/grid.png').exists()
    cli._engine = None
    rows = call('list_episodes')['episodes']
    assert len(rows) == 1
    assert call('get_episode', episode_dir=rows[0]['path'])['meta']['album_name'] == '可迁移作品'
    assert call('library_status')['root'] == str(target)
    assert str(cli._ensure_engine().config.paths.output_root).startswith(str(target.parent / '.sticker-maker-workspaces'))
    assert not list((state / 'resource_library/library/objects').rglob('*' + __import__('hashlib').sha256(b'raw').hexdigest()))
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'device_b'))
    cli._engine = None
    call('library_bind_account', account='a@example.com', confirm_legacy=True)
    call('library_connect', path=str(target))
    second = call('list_episodes')['episodes']
    assert len(second) == 1 and second[0]['work_id'] == rows[0]['work_id']
    assert (Path(second[0]['path']) / '原图/grid.png').read_bytes() == b'raw'


def test_super_export_preview_counts_shared_settings_and_history(tmp_path, monkeypatch):
    from sticker_engine.library.runtime import LibraryRuntime
    from sticker_engine.library.commands import dispatch
    from sticker_engine.config.series import save_meta, EpisodeMeta
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'device'))
    monkeypatch.setattr(cli, '_engine', None)
    rt = LibraryRuntime(tmp_path / 'device')
    old = rt.user_data / 'episodes/episode_original'
    save_meta(old, EpisodeMeta(album_name='作品'))
    (old / 'raw.png').write_bytes(b'raw')
    rt.bind('a@example.com', True)
    large = tmp_path / 'large.png'; large.write_bytes(b'original-base' * 10000)
    rt.library.write_revision(rt.account_id, 'settings-extra', {
        'kind': 'settings', 'setting_type': 'base', 'logical_path': 'custom_bases/base.png'},
        {'custom_bases/base.png': rt.library.put_file(large)}, parents=[])
    plan = dispatch(cli, 'preview', 'preview', {'target': str(tmp_path / 'backup'), 'mode': 'backup'})
    assert plan['bytes'] >= large.stat().st_size
    assert any('objects/' in entry['logical_path'] for entry in plan['entries'])


def test_export_missing_external_asset_blocks_execution(tmp_path, monkeypatch):
    import pytest
    from sticker_engine.library.runtime import LibraryRuntime
    from sticker_engine.library.commands import dispatch
    from sticker_engine.config.series import save_meta, EpisodeMeta
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'device'))
    monkeypatch.setattr(cli, '_engine', None)
    rt = LibraryRuntime(tmp_path / 'device')
    old = rt.user_data / 'episodes/episode_original'
    save_meta(old, EpisodeMeta(album_name='作品', cover_custom=str(tmp_path / 'absent.png')))
    (old / 'raw.png').write_bytes(b'raw')
    rt.bind('a@example.com', True)
    plan = dispatch(cli, 'preview', 'preview', {'target': str(tmp_path / 'backup')})
    assert plan['blocked_resources']
    with pytest.raises(ValueError, match='缺失资源'):
        dispatch(cli, 'execute', 'execute', {'plan_id': plan['plan_id']})
    assert (old / 'raw.png').exists()


def test_cache_cleanup_failure_remains_a_resumable_task(tmp_path, monkeypatch):
    from sticker_engine.library.runtime import LibraryRuntime
    from sticker_engine.library.commands import dispatch
    from sticker_engine.library.transfer import TransferManager
    from sticker_engine.library import maintenance
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'device'))
    monkeypatch.setattr(cli, '_engine', None)
    rt = LibraryRuntime(tmp_path / 'device'); rt.bind('a@example.com', True)
    plan = dispatch(cli, 'preview', 'preview', {'target': str(tmp_path / 'shared'),
                                              'mode': 'migration', 'cleanup': True})
    monkeypatch.setattr(maintenance, 'cleanup_cache_plan',
                        lambda *args: {'cleaned': 0, 'errors': ['source busy']})
    result = dispatch(cli, 'execute', 'execute', {'plan_id': plan['plan_id']})
    assert result['state'] == 'cleanup_partial'
    saved = TransferManager(rt.local / 'transfers')._load_plan(plan['plan_id'])
    assert saved['state'] == 'cleanup_partial' and saved['last_errors'] == ['source busy']
    monkeypatch.setattr(maintenance, 'cleanup_cache_plan',
                        lambda *args: {'cleaned': 1, 'errors': []})
    assert dispatch(cli, 'execute', 'retry', {'plan_id': plan['plan_id']})['state'] == 'completed'
