import pytest
from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.publish.batch import BatchPublisher
from sticker_engine.config.series import EpisodeMeta, save_meta


def test_batch_resolves_portable_episode_uuid_by_metadata_number(tmp_path, monkeypatch):
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    path = rt.output_root / 'episode_abcdef'
    save_meta(path, EpisodeMeta(album_name='第12弹', number=12, series_id='series-a'))
    (path / 'raw.png').write_bytes(b'raw')
    rt.capture(path)
    batch = BatchPublisher(None, tmp_path / 'old-location')
    assert batch.list_episodes(12, 12) == [(12, path)]
    assert batch._find_episode(12) == path


def test_batch_does_not_pick_arbitrary_work_when_numbers_are_ambiguous(tmp_path, monkeypatch):
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path))
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    for n in range(2):
        path = rt.output_root / f'episode_duplicate{n}'
        save_meta(path, EpisodeMeta(album_name=f'作品{n}', number=12, series_id=f'series-{n}'))
        (path / 'raw.png').write_bytes(b'raw'); rt.capture(path)
    with pytest.raises(ValueError, match='编号'):
        BatchPublisher(None, rt.output_root)._find_episode(12)
