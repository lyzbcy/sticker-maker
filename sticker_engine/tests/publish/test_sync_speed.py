import asyncio
import threading
import time
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse

import pytest

from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta
from sticker_engine.publish import platform_data as data
from sticker_engine.publish.parallel_read import _download_details


def row(n, status=5):
    return {'StikerID': str(n), 'Name': f'作品{n}', 'Status': status}


def test_all_platform_list_statuses_are_known():
    rows = [row(n, n) for n in range(1, 12)]
    assert data.parse_list({'base_resp': {'ret': 0}, 'List': rows}) == rows
    assert data.STATUS[11] == '限制投稿'
    assert data.STATUS[6] == '已预约上架'


def test_605_rows_with_status_11_need_zero_detail_requests(tmp_path):
    rows = [row(n, 11 if n == 604 else 4) for n in range(605)]
    for r in rows:
        save_meta(tmp_path / f'episode_{r["StikerID"]}', EpisodeMeta(
            album_name=r['Name'], platform_item_id=r['StikerID']))
    rows = data.parse_list({'base_resp': {'ret': 0}, 'List': rows}, allow_unknown=True)
    result = data.sync_rows(None, tmp_path, rows, lambda _: None, fetch_reasons=False)
    assert result['updated'] == 605 and result['source'] == 'api'
    assert result['complete'] and result['list_complete']
    assert result['reasons_total'] == 0
    assert load_meta(tmp_path / 'episode_604').platform_status == '限制投稿'


def test_future_unknown_status_is_isolated_and_never_marked_complete(tmp_path):
    for n in (1, 2):
        save_meta(tmp_path / f'episode_{n}', EpisodeMeta(album_name=f'作品{n}',
            platform_item_id=str(n), platform_status='已保存'))
    original = (tmp_path / 'episode_2/meta.json').read_bytes()
    rows = data.parse_list({'base_resp': {'ret': 0}, 'List': [row(1), row(2, 999)]}, allow_unknown=True)
    result = data.sync_rows(None, tmp_path, rows, lambda _: None, fetch_reasons=False)
    assert result['updated'] == 1 and result['platform_total'] == 2
    assert not result['list_complete'] and not result['complete']
    assert result['unknown_statuses'][0]['status_code'] == 999
    assert (tmp_path / 'episode_2/meta.json').read_bytes() == original
    with pytest.raises(data.PlatformDataError):
        data.parse_list({'base_resp': {'ret': 0}, 'List': [row(1), row(1)]}, allow_unknown=True)


@pytest.mark.parametrize('args,expected', [({}, False), ({'fetch_reasons': False}, False),
                                        ({'fetch_reasons': True}, True)])
def test_cli_reasons_are_opt_in(tmp_path, monkeypatch, args, expected):
    from sticker_engine import cli
    from sticker_engine.publish import status
    seen = []
    monkeypatch.setattr(cli, '_ensure_engine', lambda: NS(config=NS(paths=NS(output_root=tmp_path))))
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: None)
    monkeypatch.setattr(status, 'sync_status', lambda *a, **kw: seen.append(kw) or {'source': 'api'})
    result = cli.cmd_sync_platform_status('speed', args)
    assert result['source'] == 'api' and seen[0]['fetch_reasons'] is expected


@pytest.mark.parametrize('trusted', [True, False])
def test_api_first_requires_account_proof(tmp_path, monkeypatch, trusted):
    from sticker_engine.publish import status, browser
    import playwright.sync_api
    calls = []
    save_meta(tmp_path / 'episode_1', EpisodeMeta(album_name='作品1', platform_item_id='1'))
    class Session:
        can_reuse_session = trusted
        def __init__(self, *a, **kw): pass
        def start(self): calls.append('start'); return None
        def ensure_login(self, *a, **kw): calls.append('login'); return True
        def close(self): calls.append('close')
    class PW:
        def __enter__(self): return None
        def __exit__(self, *a): pass
    def read(*a):
        calls.append('api')
        return {'base_resp': {'ret': 0}, 'List': [row(1)]}
    monkeypatch.setattr(browser, 'BrowserSession', Session)
    monkeypatch.setattr(playwright.sync_api, 'sync_playwright', PW)
    monkeypatch.setattr(data, 'read_json', read)
    monkeypatch.setattr(status, 'fetch_income', lambda *a, **kw: {})
    monkeypatch.setattr(status, '_sync_status_legacy', lambda *a, **kw: pytest.fail('no DOM fallback'))
    engine = NS(config=NS(paths=NS(output_root=tmp_path)))
    result = status.sync_status(engine, fetch_reasons=False)
    assert result['updated'] == 1
    assert calls == (['start', 'api', 'close'] if trusted else ['start', 'login', 'api', 'close'])


class Response:
    def __init__(self, sid, status=200):
        self.sid = sid
        self.status = status
        self.ok = status == 200
        self.headers = {'retry-after': '1'}
        self.disposed = False
    async def json(self):
        return {'base_resp': {'ret': 0}, 'StikerID': self.sid, 'Status': 4, 'Reason': {'paneliconurl': ['reason']}}
    async def dispose(self): self.disposed = True


class Client:
    def __init__(self, delay=.03, fail=None):
        self.delay, self.fail = delay, fail
        self.active = self.peak = 0
        self.calls, self.responses = [], []
    async def get(self, url, **kw):
        assert kw['max_redirects'] == 0
        sid = parse_qs(urlparse(url).query)['stikerid'][0]
        self.calls.append(sid)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            response = Response(sid, self.fail(sid, self.calls.count(sid)) if self.fail else 200)
            self.responses.append(response)
            return response
        finally:
            self.active -= 1


def test_parallel_details_bound_to_three_and_dispose_responses():
    c, results = Client(), []
    asyncio.run(_download_details(c, list(map(str, range(15))), threading.Event(), results.append))
    assert c.peak == 3
    assert len([r for kind, r in results if kind == 'result']) == 15
    assert all(r.disposed for r in c.responses)


def test_cancel_aborts_inflight_and_stops_queued_requests():
    c, event, results = Client(delay=5), threading.Event(), []
    async def run():
        task = asyncio.create_task(_download_details(c, list(map(str, range(20))), event, results.append))
        await asyncio.sleep(.05)
        t = time.monotonic()
        event.set()
        await task
        return time.monotonic() - t
    assert asyncio.run(run()) < .5
    assert len(c.calls) == 3 and c.active == 0
    assert results == []


def test_rate_limit_retries_and_reduces_concurrency():
    c, results = Client(fail=lambda sid, attempt: 429 if sid == '0' and attempt == 1 else 200), []
    asyncio.run(_download_details(c, list(map(str, range(10))), threading.Event(), results.append))
    assert c.calls.count('0') == 2
    assert len([r for kind, r in results if kind == 'result']) == 10
    assert any(kind == 'notice' for kind, _ in results)
    assert c.peak <= 3


def test_detail_failure_does_not_cancel_other_items():
    c, results = Client(fail=lambda sid, attempt: 500 if sid == '1' else 200), []
    asyncio.run(_download_details(c, ['0', '1', '2'], threading.Event(), results.append))
    result = {r[0]: r for kind, r in results if kind == 'result'}
    assert result['1'][2] is not None and result['0'][2] is None and result['2'][2] is None


def test_cancel_before_start_launches_no_browser(tmp_path, monkeypatch):
    from sticker_engine.publish.status import sync_status
    from sticker_engine.publish.browser import BrowserSession
    monkeypatch.setattr(BrowserSession, 'start', lambda *a: pytest.fail('cancelled'))
    r = sync_status(NS(config=NS(paths=NS(output_root=tmp_path))), should_stop=lambda: True)
    assert r['cancelled'] and r['updated'] == 0


def test_state_only_preserves_existing_cached_rejection(tmp_path):
    path = tmp_path / 'episode_1'
    save_meta(path, EpisodeMeta(album_name='作品1', platform_item_id='1',
        platform_status='未通过审核', platform_review_cycle='cycle',
        platform_reject_checked_cycle='cycle', platform_reject_reason='old reason'))
    result = data.sync_rows(None, tmp_path, [row(1, 4)], lambda _: None, fetch_reasons=False)
    assert result['reasons_fetched'] == 0
    assert load_meta(path).platform_reject_reason == 'old reason'


def test_cache_hit_does_not_rewrite_review_observation_time(tmp_path):
    path = tmp_path / 'episode_1'
    meta = EpisodeMeta(album_name='作品1', platform_item_id='1',
        platform_status='未通过审核', platform_review_cycle='cycle',
        platform_reject_checked_cycle='cycle', platform_reject_reason='old reason',
        platform_review_history=[{'cycle': 'cycle', 'reason': 'old reason', 'last_seen_at': 'original'}])
    save_meta(path, meta)
    result = data.sync_rows(None, tmp_path, [row(1, 4)], lambda _: None)
    assert result['reasons_skipped'] == 1
    assert load_meta(path).platform_review_history[0]['last_seen_at'] == 'original'


def test_committed_platform_metadata_skips_full_post_scan(monkeypatch):
    from sticker_engine.library import hooks
    calls = []
    rt = NS(refresh=lambda **kw: calls.append(kw) or {}, require_account=lambda: None, library=object())
    monkeypatch.setattr(hooks, 'runtime_for', lambda engine: rt)
    cli = NS(_ensure_engine=lambda: None, _stop_events={}, _emit=lambda event: None)
    result = hooks.invoke(cli, 'fast', 'sync_platform_status', {},
                          lambda *a: {'metadata_committed': True})
    assert result['metadata_committed']
    assert calls == []  # metadata sync does not scan/materialize artwork before or after


def test_cancel_during_preparation_does_not_start_handler(monkeypatch):
    from sticker_engine.library import hooks
    stop, results = threading.Event(), []
    def check_account(): stop.set()
    monkeypatch.setattr(hooks, 'runtime_for', lambda engine: NS(require_account=check_account, library=object()))
    cli = NS(_ensure_engine=lambda: None, _stop_events={'stop': stop},
             _emit=lambda event: None, _result=lambda *a, **kw: results.append(kw['data']))
    hooks.invoke(cli, 'stop', 'sync_platform_status', {}, lambda *a: pytest.fail('must cancel before network'))
    assert results[0]['cancelled'] and results[0]['updated'] == 0
