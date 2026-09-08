import pytest
from sticker_engine.library.runtime import LibraryRuntime


def test_uncertain_submit_blocks_retry_and_can_be_reconciled(tmp_path):
    from sticker_engine.library.operations import begin, finish, unresolved, reconcile
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    p = rt.placeholder({'StikerID':'s1','Name':'作品'})
    capture = rt.capture(p)
    op = begin(rt, capture['work_id'], '作品')
    finish(rt, op, False)
    assert unresolved(rt)[0]['phase'] == 'unknown'
    with pytest.raises(ValueError, match='核对'):
        begin(rt, capture['work_id'], '作品')
    reconcile(rt, op, 'not_submitted')
    assert unresolved(rt) == []


def test_operation_results_follow_library_merge(tmp_path):
    from sticker_engine.library.operations import begin, unresolved
    a=LibraryRuntime(tmp_path/'a'); a.bind('a@example.com', True)
    b=LibraryRuntime(tmp_path/'b'); b.bind('a@example.com', True)
    begin(a, 'work', '作品')
    b.library.merge_from(a.library)
    assert unresolved(b)[0]['work_id'] == 'work'


def test_duplicate_series_number_blocks_before_platform_read(tmp_path, monkeypatch):
    from sticker_engine.library.operations import verify_target
    from sticker_engine.config.series import EpisodeMeta, save_meta
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    for i in range(2):
        path = rt.output_root / f'episode_{i}'
        save_meta(path, EpisodeMeta(album_name=f'作品{i}', series_id='series', number=12))
        (path / 'raw.png').write_bytes(b'raw')
        rt.capture(path)
    def no_network(*_):
        raise AssertionError('duplicate must be rejected before network')
    monkeypatch.setattr('sticker_engine.publish.platform_data.read_json', no_network)
    with pytest.raises(ValueError, match='编号'):
        verify_target(rt, None, path, False)


def test_publish_preflight_error_returns_result_when_recapture_also_fails(tmp_path, monkeypatch):
    from sticker_engine.publish.publisher import Publisher
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    monkeypatch.setattr('sticker_engine.library.runtime.active_runtime', lambda: rt)
    monkeypatch.setattr(rt, 'capture', lambda *_: (_ for _ in ()).throw(ValueError('missing source')))
    publisher = Publisher(None, None)
    result = publisher.publish(tmp_path / 'absent')
    assert result['success'] is False
    assert 'missing source' in result['error']


def test_concurrent_operation_results_require_reconcile(tmp_path):
    from sticker_engine.library.operations import begin, finish, unresolved
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    op = begin(rt, 'work', '作品')
    intent = rt.library.read_work(rt.account_id, op)['revision']
    for phase in ('succeeded', 'confirmed_not_submitted'):
        rt.library.write_revision(rt.account_id, op, dict(intent['metadata'], phase=phase), {},
                                  parents=[intent['revision_id']])
    assert unresolved(rt)[0]['operation_id'] == op
    result = finish(rt, op, True)
    assert result['phase'] == 'unknown'
    assert rt.library.read_work(rt.account_id, op)['state'] == 'conflict'


def test_pending_platform_review_is_not_resubmitted(tmp_path, monkeypatch):
    from sticker_engine.library.operations import verify_target
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    path = rt.placeholder({'StikerID': 'platform1', 'Name': '作品'})
    rt.capture(path)
    monkeypatch.setattr('sticker_engine.publish.platform_data.read_json', lambda *_: {
        'base_resp': {'ret': 0}, 'List': [{'StikerID': 'platform1', 'Name': '作品', 'Status': 2}]})
    with pytest.raises(ValueError, match='待审核'):
        verify_target(rt, None, path, True)


def test_direct_publisher_checks_runtime_capabilities_before_browser(tmp_path, monkeypatch):
    from sticker_engine.publish.publisher import Publisher
    from sticker_engine.config.series import EpisodeMeta, save_meta
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    path = rt.output_root / 'episode_incomplete'
    save_meta(path, EpisodeMeta(album_name='素材不全'))
    (path / 'raw.png').write_bytes(b'raw only')
    rt.capture(path)
    monkeypatch.setattr('sticker_engine.library.runtime.active_runtime', lambda: rt)
    publisher = Publisher(None, None)
    def forbidden(*_):
        raise AssertionError('browser invoked before resource validation')
    monkeypatch.setattr(publisher, '_publish_impl', forbidden)
    result = publisher.publish(path)
    assert result['success'] is False
    assert '素材' in result['error']
    assert 'browser invoked' not in result['error']
