import pytest
from sticker_engine.publish.status import parse_rows_from_text
from sticker_engine.publish.platform_data import STATUS, sync_rows
from sticker_engine.config.series import EpisodeMeta, save_meta, load_meta


@pytest.mark.parametrize('status', list(STATUS.values()))
def test_dom_recognizes_every_platform_state(status):
    rows = parse_rows_from_text(f'星星布丁第6弹\n-\t-\t-\t{status}\t原创\t2026-10-19\t详情')
    assert len(rows) == 1
    assert rows[0].status == status


def test_failed_reservation_is_submitted_not_live_or_rejected(tmp_path):
    episode = tmp_path / 'episode_failed'
    save_meta(episode, EpisodeMeta(album_name='星星布丁第6弹',
        platform_item_id='failed-id', published=False, platform_reject_reason='旧审核理由'))
    result = sync_rows(None, tmp_path, [{'StikerID': 'failed-id',
        'Name': '星星布丁第6弹', 'Status': 10}], lambda _: None,
        fetch_reasons=True, detail_reader=lambda _: pytest.fail('no rejection lookup'))
    meta = load_meta(episode)
    assert meta.platform_status == '预约上架失败'
    assert meta.published is True
    assert meta.platform_item_id == 'failed-id'
    assert meta.platform_reject_reason == ''
    assert result['fresh_passed'] == []
    assert result['fresh_shelfable'] == [str(episode)]
    assert result['complete'] is True


@pytest.mark.parametrize('edit', [False, True])
def test_failed_reservation_never_enters_publisher(tmp_path, monkeypatch, edit):
    from sticker_engine.publish.publisher import Publisher
    from sticker_engine.library import runtime
    save_meta(tmp_path, EpisodeMeta(album_name='星星布丁第6弹',
        platform_status='预约上架失败', platform_item_id='failed-id'))
    monkeypatch.setattr(runtime, 'active_runtime', lambda: pytest.fail('must stop before library/browser'))
    publisher = Publisher.__new__(Publisher)
    result = publisher.publish(tmp_path, edit=edit)
    assert result['success'] is False
    assert result['step'] == 'prepare'
    assert '预约上架失败' in result['error']
