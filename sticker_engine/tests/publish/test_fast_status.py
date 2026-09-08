import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta, mark_published


def service():
    from sticker_engine.publish import platform_data
    return platform_data


def row(n=5, status=4, date='2026-09-07'):
    return dict(StikerID=f'stiker_{n}', Name=f'作品{n}', Status=status,
                ModifyTime=date, DownloadNum=0, SendNum=0, Rewards='0',
                TotalDownloadNum='68', TotalSendNum='214')


def episode(root, n=5):
    path = root / f'episode_{n}'
    save_meta(path, EpisodeMeta(album_name=f'作品{n}'))
    return path


class Response:
    ok = True
    def __init__(self, body): self.body = body
    def json(self): return self.body


class Page:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.fail_ids = set()
        self.context = SimpleNamespace(request=self)
    def get(self, url, **kwargs):
        self.calls.append(url)
        if '/home?' in url:
            return Response({'base_resp': {'ret': 0}, 'List': self.rows})
        from urllib.parse import parse_qs, urlparse
        sid = parse_qs(urlparse(url).query)['stikerid'][0]
        if sid in self.fail_ids: raise RuntimeError('network failed')
        item = next(r for r in self.rows if r['StikerID'] == sid)
        return Response({'base_resp': {'ret': 0}, 'StikerID': sid,
                         'Status': item['Status'], 'Reason': json.dumps({'paneliconurl': ['同样的图标理由']})})


def test_all_303_and_second_sync_skips_cached_reasons(tmp_path):
    for n in range(303): episode(tmp_path, n)
    p = Page([row(n) for n in range(303)])
    first = service().sync_page(p, tmp_path)
    assert first['matched'] == 303 and first['reasons_fetched'] == 303
    p.calls.clear()
    second = service().sync_page(p, tmp_path)
    assert len(p.calls) == 1
    assert second['reasons_skipped'] == 303
    assert len(load_meta(tmp_path / 'episode_5').platform_review_history) == 1


def test_status_only_never_requests_reason(tmp_path):
    episode(tmp_path)
    p = Page([row()])
    result = service().sync_page(p, tmp_path, fetch_reasons=False)
    assert len(p.calls) == 1 and result['reasons_fetched'] == 0


def test_new_submission_same_reason_is_new_history(tmp_path):
    ep = episode(tmp_path)
    p = Page([row()])
    service().sync_page(p, tmp_path)
    mark_published(ep)
    service().sync_page(p, tmp_path)
    history = load_meta(ep).platform_review_history
    assert len(history) == 2
    assert history[0]['reason'] == history[1]['reason']
    assert history[0]['cycle'] != history[1]['cycle']
    assert history[0]['round'] is None
    assert history[1]['round'] == 1


def test_pending_observed_does_not_double_count_local_submission(tmp_path):
    ep = episode(tmp_path)
    p = Page([row()])
    service().sync_page(p, tmp_path)
    mark_published(ep)
    p.rows = [row(status=2)]
    service().sync_page(p, tmp_path)
    p.rows = [row()]
    service().sync_page(p, tmp_path)
    assert load_meta(ep).platform_review_round == 1
    assert len(load_meta(ep).platform_review_history) == 2


def test_force_refresh_updates_same_cycle_not_new_round(tmp_path):
    ep = episode(tmp_path)
    p = Page([row()])
    service().sync_page(p, tmp_path)
    service().sync_page(p, tmp_path, force_reasons=True)
    assert len(load_meta(ep).platform_review_history) == 1


def test_date_change_is_unknown_cycle_not_invented_round(tmp_path):
    ep = episode(tmp_path)
    p = Page([row()])
    service().sync_page(p, tmp_path)
    p.rows = [row(date='2026-09-08')]
    service().sync_page(p, tmp_path)
    m = load_meta(ep)
    assert len(m.platform_review_history) == 2
    assert m.platform_review_history[-1]['round'] is None


def test_failed_reason_keeps_states_and_retries_only_failure(tmp_path):
    for n in (5, 57): episode(tmp_path, n)
    p = Page([row(5), row(57)])
    p.fail_ids.add('stiker_57')
    result = service().sync_page(p, tmp_path)
    assert result['complete'] is False and len(result['reason_failures']) == 1
    assert load_meta(tmp_path / 'episode_57').platform_status == '未通过审核'
    assert load_meta(tmp_path / 'episode_5').platform_reject_reason
    p.fail_ids.clear()
    p.calls.clear()
    result = service().sync_page(p, tmp_path)
    assert result['reasons_fetched'] == 1 and result['reasons_skipped'] == 1


def test_identity_no_prefix_or_ambiguous_name_binding(tmp_path):
    ep = episode(tmp_path, 5)
    p = Page([row(57)])
    assert service().sync_page(p, tmp_path)['matched'] == 0
    assert not load_meta(ep).platform_item_id
    p.rows = [row(5), dict(row(5), StikerID='another')]
    assert service().sync_page(p, tmp_path)['matched'] == 0


def test_api_error_and_duplicate_ids_are_not_valid_lists():
    mod = service()
    for body in ({'base_resp': {'ret': -1}, 'List': []}, {},
                 {'base_resp': {'ret': 0}, 'List': [row(), row()]}):
        with pytest.raises(mod.PlatformDataError): mod.parse_list(body)


def test_reason_preserves_full_text_and_group():
    reason = service().parse_reason(json.dumps({'paneliconurl': ['长' * 700]}))
    assert '聊天页图标' in reason and '长' * 700 in reason


def test_shelf_entry_requests_only_fresh_status_and_stops_on_error(tmp_path, monkeypatch):
    import sticker_engine.cli as cli
    import sticker_engine.publish.status as status
    ep = episode(tmp_path)
    m = load_meta(ep); m.platform_status = '审核通过'; save_meta(ep, m)
    monkeypatch.setattr(cli, '_ensure_engine', lambda: SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(output_root=tmp_path))))
    called = []
    def sync(*a, **kw):
        called.append(kw)
        return {'error': '登录失败', 'complete': False}
    monkeypatch.setattr(status, 'sync_status', sync)
    results = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: results.append((a, kw)))
    cli.cmd_shelf_passed('t', {})
    assert called[0]['fetch_reasons'] is False
    assert results[0][0][1] == 'fail'


def test_sync_cancel_keeps_partial_reasons(tmp_path):
    for n in (5, 57): episode(tmp_path, n)
    p = Page([row(5), row(57)])
    fetched = []
    def should_stop():
        return len(fetched) >= 1   # 第一单理由读完后取消
    original = p.get
    def get(url, **kw):
        r = original(url, **kw)
        if 'stikerid' in url: fetched.append(url)
        return r
    p.get = get
    result = service().sync_page(p, tmp_path, should_stop=should_stop)
    assert result['cancelled'] is True and result['complete'] is False
    assert result['reasons_fetched'] == 1
    # 状态是全量回写的（第一批先落库），理由只落了取消前的
    assert load_meta(tmp_path / 'episode_5').platform_reject_reason
    assert load_meta(tmp_path / 'episode_57').platform_reject_reason == ''
    assert load_meta(tmp_path / 'episode_57').platform_status == '未通过审核'


def test_platform_commands_are_exclusive(monkeypatch, tmp_path):
    import sticker_engine.cli as cli
    import sticker_engine.publish.status as status
    monkeypatch.setattr(cli, '_ensure_engine', lambda: SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(output_root=tmp_path))))
    ran = []
    monkeypatch.setattr(status, 'sync_status',
                        lambda *a, **kw: ran.append(kw) or {'matched': 0})
    results = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: results.append((a, kw)))
    with cli._platform_exclusive('提交作品(发布)', 'other'):
        cli.cmd_sync_platform_status('t2', {})   # 互斥期内必须立刻失败，不排队
    assert ran == []   # 没有真正跑同步
    assert results[0][0][1] == 'fail'
    assert '平台操作正在执行' in results[0][1]['errors'][0]['message']
    # 锁释放后可正常执行
    cli.cmd_sync_platform_status('t3', {})
    assert len(ran) == 1 and results[1][0][1] == 'ok'


def test_fix_republish_publish_step_is_exclusive(tmp_path, monkeypatch):
    """编辑器重提段抢不到锁必须立刻失败且锁不泄漏（评审 P1-4）。"""
    import sticker_engine.cli as cli
    ep = episode(tmp_path)
    m = load_meta(ep)
    m.platform_status = '未通过审核'
    m.platform_reject_reason = '表情名称应避免出现空格'
    m.album_name = '作品5'
    save_meta(ep, m)
    monkeypatch.setattr(cli, '_ensure_engine', lambda: SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(output_root=tmp_path))))
    results = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: results.append((a, kw)))
    with cli._platform_exclusive('一键更新(同步)', 'other'):
        cli.cmd_fix_and_republish('t', {'episode_dir': str(ep), 'publish': True})
    assert results[0][0][1] == 'fail'
    assert '平台操作正在执行' in str(results[0][1])
    # 锁已释放：另一个命令能正常拿锁
    with cli._platform_exclusive('x', 'x2'):
        pass


def test_shelf_sync_phase_makes_zero_detail_requests(tmp_path, monkeypatch):
    """一键发布入口的同步阶段零理由/详情请求（验收项硬断言，评审 P2-3）。"""
    import sticker_engine.cli as cli
    import sticker_engine.publish.status as status
    from types import SimpleNamespace as NS
    ep = episode(tmp_path)
    m = load_meta(ep)
    m.platform_status = '已上架'
    save_meta(ep, m)
    p = Page([row(5, status=7)])   # 已上架：不触发理由抓取

    def real_sync(engine, on_status=None, fetch_reasons=True, should_stop=None, **kw):
        assert fetch_reasons is False
        from sticker_engine.publish import platform_data
        return platform_data.sync_page(p, tmp_path, on_status=on_status,
                                       fetch_reasons=fetch_reasons,
                                       should_stop=should_stop)

    monkeypatch.setattr(status, 'sync_status', real_sync)
    monkeypatch.setattr(cli, '_ensure_engine',
                        lambda: NS(config=NS(paths=NS(output_root=tmp_path))))
    results = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: results.append((a, kw)))
    cli.cmd_shelf_passed('t', {})
    assert len(p.calls) == 1 and '/home?' in p.calls[0]   # 只有列表，无 stikerpage
    assert results[0][0][1] == 'ok'   # 无审核通过单：正常完成，未误报失败


def test_shelf_cancel_keeps_completed_items(tmp_path, monkeypatch):
    import threading
    import sticker_engine.cli as cli
    from types import SimpleNamespace as NS
    eps = []
    for n in (1, 2, 3):
        ep = episode(tmp_path, n)
        m = load_meta(ep)
        m.platform_status = '审核通过'
        m.platform_item_id = f'stiker_{n}'
        m.album_name = f'作品{n}'
        save_meta(ep, m)
        eps.append(ep)

    def fake_sync(engine, on_status=None, fetch_reasons=True, should_stop=None, **kw):
        return {'list_complete': True, 'fresh_passed': [str(e) for e in eps]}

    monkeypatch.setattr(cli, '_ensure_engine',
                        lambda: NS(config=NS(paths=NS(output_root=tmp_path))))

    # 假 Playwright：第二单「预约」点击成功后触发取消
    state = {'done': 0}
    stop = threading.Event()
    trigger = {}

    class FakeLocator:
        def __init__(self): self._clicked = [0]
        def wait_for(self, **kw): pass
        def count(self): return 1
        @property
        def first(self): return self
        def click(self):
            state['done'] += 1
            # 每单两次点击（上架 + 预约）；第二单预约后（第 4 次）触发取消
            if state['done'] == 4:
                trigger['fire']()

    class FakePage:
        def __init__(self):
            self.context = NS(request=self)   # read_detail 走 page.context.request
        def get(self, url, **kw):
            sid = url.split('stikerid=')[1].split('&')[0]
            return Response({'base_resp': {'ret': 0}, 'StikerID': sid, 'Status': 5})
        def goto(self, *a, **kw): pass
        def get_by_role(self, *a, **kw): return NS(wait_for=lambda **kw: None)
        def locator(self, *a, **kw): return FakeLocator()
        def wait_for_timeout(self, *a): pass
        def inner_text(self, *a): return '预约成功'

    class FakeSession:
        def start(self): return FakePage()
        def ensure_login(self, page, on_status=None): return True
        def close(self): pass

    import sticker_engine.publish.browser as browser_mod
    import playwright.sync_api as pw_mod

    class _Ctx:   # with 语句的特殊方法在类上查找，不能用 SimpleNamespace
        def __enter__(self): return None
        def __exit__(self, *a): return False

    monkeypatch.setattr(browser_mod, 'BrowserSession', lambda *a, **kw: FakeSession())
    monkeypatch.setattr(pw_mod, 'sync_playwright', lambda: _Ctx())
    results = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: results.append((a, kw)))

    # 直接注入 stop（_run_shelf_passed 支持），第二单预约后触发取消
    trigger['fire'] = stop.set
    cli._run_shelf_passed('t', {}, tmp_path, fake_sync,
                          lambda msg: None, stop=stop)
    data = [kw.get('data') or {} for a, kw in results if a[1] == 'ok'][0]
    assert data['cancelled'] is True
    assert data['published'] == 2          # 前两单已完成并落库
    assert len(data['remaining']) == 1     # 第三单保留未处理
    assert load_meta(eps[1]).platform_status == '已上架'
    assert load_meta(eps[2]).platform_status == '审核通过'
