import yaml
from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.library.settings import settings_dir


def set_grid(runtime, value):
    path = settings_dir(runtime) / 'prefs.yaml'
    payload = yaml.safe_load(path.read_text()) or {}
    payload['grid_size'] = value
    path.write_text(yaml.safe_dump(payload))


def test_bound_devices_share_preferences_and_resolve_concurrent_edits(tmp_path):
    a = LibraryRuntime(tmp_path / 'a')
    a.user_data.mkdir()
    (a.user_data / 'prefs.yaml').write_text('grid_size: 3\n')
    a.bind('a@example.com', True)
    b = LibraryRuntime(tmp_path / 'b'); b.bind('a@example.com', True)
    b.connect(a.library.root)
    assert yaml.safe_load((settings_dir(b) / 'prefs.yaml').read_text())['grid_size'] == 3
    set_grid(a, 2)
    set_grid(b, 4)
    a.capture_all(); b.capture_all()
    conflicts = a.status()['settings_conflicts']
    assert len(conflicts) == 1
    chosen = next(rev for rev in conflicts[0]['heads'] if rev['metadata']['payload']['grid_size'] == 4)
    a.resolve(conflicts[0]['work_id'], chosen['revision_id'])
    a.refresh()
    assert yaml.safe_load((settings_dir(a) / 'prefs.yaml').read_text())['grid_size'] == 4
    assert a.status()['settings_conflicts'] == []
    b.refresh()
    assert b.status()['settings_conflicts'] == []
