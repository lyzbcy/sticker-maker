from pathlib import Path
from types import SimpleNamespace
from sticker_engine.api import StickerEngine, Episode
from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.config.series import EpisodeMeta, save_meta


def test_direct_engine_run_captures_each_output_before_return(tmp_path, monkeypatch):
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    engine = StickerEngine(SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path)))
    output = rt.output_root / 'episode_generated'
    def generate(**kwargs):
        save_meta(output, EpisodeMeta(album_name='新作品'))
        (output / 'raw.png').write_bytes(b'new image')
        return Episode(episode_dir=output)
    monkeypatch.setattr(engine, '_run_impl', generate, raising=False)
    result = engine.run()
    assert result.success
    assert LibraryRuntime(tmp_path).rows()[0]['album_name'] == '新作品'


def test_capture_failure_is_reported_without_losing_generated_path(tmp_path, monkeypatch):
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    engine = StickerEngine(SimpleNamespace(paths=SimpleNamespace(user_data=tmp_path)))
    output = rt.output_root / 'episode_generated'
    def generate(**kwargs):
        save_meta(output, EpisodeMeta(album_name='新作品'))
        return Episode(episode_dir=output)
    monkeypatch.setattr(engine, '_run_impl', generate, raising=False)
    monkeypatch.setattr(LibraryRuntime, 'capture', lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    result = engine.run()
    assert not result.success
    assert result.episode_dir == output
    assert 'disk full' in result.aborted_reason
