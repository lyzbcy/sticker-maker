from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.publish.shelf import Shelf
from sticker_engine import cli


def test_bound_shelf_uses_account_pipeline_and_preserves_limit_and_dry_run(tmp_path, monkeypatch):
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    monkeypatch.setattr(cli, '_engine', None)
    seen = {}
    def run(req, args, root, sync, say, stop=None, result_callback=None):
        seen.update(args=args, root=root)
        result_callback(req, 'ok', data={'published': 0, 'dry_run': True,
                                        'skipped_names': ['作品'], 'failed': []})
    monkeypatch.setattr(cli, '_run_shelf_passed', run)
    class NoLegacyBrowser:
        def start(self, **kwargs):
            raise AssertionError('legacy shelf bypassed account pipeline')
    result = Shelf(None, NoLegacyBrowser()).shelve_all(limit=1, dry_run=True, headless=True)
    assert seen['args'] == {'limit': 1, 'dry_run': True, 'headless': True}
    assert seen['root'] == rt.output_root
    assert result['summary']['skip'] == 1
    assert result['summary']['ok'] == 0


def test_bound_dry_run_limits_fresh_candidates_without_opening_shelf_browser(tmp_path, monkeypatch):
    from sticker_engine.config.series import load_meta, save_meta
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    monkeypatch.setattr(cli, '_engine', None)
    paths = []
    for n in range(2):
        path = rt.placeholder({'StikerID': str(n), 'Name': f'作品{n}'})
        meta = load_meta(path); meta.platform_status = '审核通过'
        save_meta(path, meta); rt.capture(path); paths.append(str(path))
    monkeypatch.setattr('sticker_engine.publish.status.sync_status', lambda *_args, **_kwargs: {
        'list_complete': True, 'fresh_passed': paths})
    def forbidden(*_args, **_kwargs):
        raise AssertionError('dry-run must not open shelf browser')
    monkeypatch.setattr('sticker_engine.publish.browser.BrowserSession.start', forbidden)
    result = Shelf(None, None).shelve_all(limit=1, dry_run=True)
    assert result['summary']['skip'] == 1
    assert result['summary']['ok'] == 0
    assert 'error' not in result
