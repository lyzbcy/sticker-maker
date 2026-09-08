from sticker_engine.config.series import EpisodeMeta, save_meta, load_meta
from sticker_engine.publish.platform_data import sync_rows


def test_sync_creates_missing_records_only_for_bound_account(tmp_path):
    seen = []
    def make(row):
        p = tmp_path / ('episode_' + row['StikerID'])
        save_meta(p, EpisodeMeta(album_name=row['Name'], account_id='a',
                                platform_item_id=row['StikerID'], resource_placeholder=True))
        seen.append(p)
        return p
    rows = [{'StikerID': 'one', 'Name': '作品', 'Status': 5}]
    result = sync_rows(None, tmp_path, rows, lambda m: None, fetch_reasons=False,
                       account_id='a', placeholder_factory=make)
    assert result['created'] == 1
    assert result['fresh_passed'] == [str(seen[0])]
    assert load_meta(seen[0]).platform_status == '审核通过'
    again = sync_rows(None, tmp_path, rows, lambda m: None, fetch_reasons=False,
                      account_id='a', placeholder_factory=make)
    assert again['created'] == 0


def test_sync_does_not_match_other_account_same_id(tmp_path):
    p = tmp_path / 'episode_other'
    save_meta(p, EpisodeMeta(account_id='b', platform_item_id='one', album_name='作品'))
    rows = [{'StikerID': 'one', 'Name': '作品', 'Status': 5}]
    result = sync_rows(None, tmp_path, rows, lambda m: None, fetch_reasons=False,
                       account_id='a')
    assert result['matched'] == 0
    assert load_meta(p).platform_status == ''


def test_shelf_skips_conflicted_work_even_if_platform_passed(tmp_path, monkeypatch):
    from sticker_engine.library.runtime import LibraryRuntime
    from sticker_engine import cli
    from types import SimpleNamespace
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    p = rt.placeholder({'StikerID': 'one', 'Name': '作品'})
    meta = load_meta(p); meta.platform_status = '审核通过'; save_meta(p, meta)
    first = rt.capture(p)
    for title in ('a', 'b'):
        rt.library.write_revision(rt.account_id, first['work_id'],
            {'album_name':title}, {}, parents=[first['revision_id']])
    fake=SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(
        user_data=tmp_path, output_root=rt.output_root)))
    monkeypatch.setattr(cli, '_ensure_engine', lambda: fake)
    from sticker_engine.publish.browser import BrowserSession
    def no_browser(*a, **kw):
        raise AssertionError('conflicted work must never start browser')
    monkeypatch.setattr(BrowserSession, 'start', no_browser)
    emitted=[]; monkeypatch.setattr(cli, '_emit', emitted.append)
    cli._run_shelf_passed('s', {}, rt.output_root,
        lambda *a, **kw: {'list_complete':True, 'fresh_passed':[str(p)]}, lambda m: None)
    result = emitted[-1]
    assert result['status'] == 'ok' and result['data']['published'] == 0
