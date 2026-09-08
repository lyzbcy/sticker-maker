import pytest
from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.config.series import EpisodeMeta, save_meta


@pytest.mark.parametrize('edit_during_copy', [False, True])
def test_materialization_preserves_uncaptured_local_edits(tmp_path, monkeypatch, edit_during_copy):
    rt = LibraryRuntime(tmp_path); rt.bind('a@example.com', True)
    path = rt.output_root / 'episode_one'
    save_meta(path, EpisodeMeta(album_name='one'))
    (path / 'raw.txt').write_text('original')
    first = rt.capture(path)
    source = tmp_path / 'remote.txt'; source.write_text('remote')
    revision = rt.library.read_work(rt.account_id, first['work_id'])['revision']
    rt.library.write_revision(rt.account_id, first['work_id'], revision['metadata'],
                              {'raw.txt': rt.library.put_file(source)}, parents=[first['revision_id']])
    if edit_during_copy:
        original = rt.library.materialize
        def copy_then_edit(*args, **kwargs):
            result = original(*args, **kwargs)
            (path / 'raw.txt').write_text('local edit')
            return result
        monkeypatch.setattr(rt.library, 'materialize', copy_then_edit)
    else:
        (path / 'raw.txt').write_text('local edit')
    rt.refresh(capture=False)
    assert (path / 'raw.txt').read_text() == 'local edit'
    assert rt.library.read_work(rt.account_id, first['work_id'])['state'] == 'conflict'
