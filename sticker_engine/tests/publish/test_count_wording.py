"""User-visible album units; all fixtures are independent of the real library."""
from sticker_engine.config.series import EpisodeMeta, save_meta
from sticker_engine.publish import platform_data as data


def test_sync_unknown_status_and_counts_use_dan(tmp_path):
    save_meta(tmp_path / 'episode_1', EpisodeMeta(album_name='作品1', platform_item_id='1'))
    rows = [{'StikerID': '1', 'Name': '作品1', 'Status': 5},
            {'StikerID': '2', 'Name': '作品2', 'Status': 999}]
    messages = []
    result = data.sync_rows(None, tmp_path, rows, messages.append, fetch_reasons=False)
    assert result['updated'] == 1 and not result['list_complete']
    assert '接口返回 2 弹，其中 1 弹' in messages[0]
    assert any('已更新 1 弹状态（平台共 2 弹' in m for m in messages)
    assert all(' 单' not in m for m in messages)


def test_cancelled_sync_and_reason_count_use_dan(tmp_path):
    save_meta(tmp_path / 'episode_1', EpisodeMeta(album_name='作品1', platform_item_id='1'))
    messages = []
    result = data.sync_rows(None, tmp_path,
        [{'StikerID': '1', 'Name': '作品1', 'Status': 4}], messages.append,
        should_stop=lambda: True)
    assert result['cancelled'] and result['updated'] == 0
    assert '已更新 0 弹状态，剩余 1 弹未写入' in messages[0]
    assert '已保留 0 弹理由' in messages[-1]
    assert all(' 单' not in m for m in messages)
