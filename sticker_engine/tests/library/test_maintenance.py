from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.library.maintenance import record_cache_plan, cleanup_cache_plan


def setup_plan(tmp_path, projection=False, untracked=False):
    rt = LibraryRuntime(tmp_path / 'device')
    rt.bind('test@example.com', True)
    source = rt.output_root.parent / 'settings' / 'custom_bases' / 'raw.png'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'original')
    from sticker_engine.library.settings import SharedSettings
    SharedSettings(rt).capture()
    if untracked:
        (source.parent / "untracked-copy.png").write_bytes(b"original")
    if projection:
        (source.parent / 'series.json').write_text('[{"role_asset_map": {"hero": "/local/cache/banner.png"}}]')
    target = ResourceLibrary(tmp_path / 'shared', create=True)
    target.merge_from(rt.library)
    record_cache_plan(rt, {'plan_id': 'test', 'mode': 'migration', 'cleanup': True,
                          'target': str(target.root)})
    rt.state.update(root=str(target.root), library_id=target.library_id)
    rt.save()
    return rt, source, target


def test_cleanup_preserves_source_changed_after_preview(tmp_path):
    rt, source, _ = setup_plan(tmp_path)
    source.write_bytes(b'edited after preview')
    result = cleanup_cache_plan(rt, 'test')
    assert source.read_bytes() == b'edited after preview'
    assert result['errors']


def test_cleanup_preserves_source_if_target_corrupt(tmp_path):
    rt, source, target = setup_plan(tmp_path)
    for obj in (target.root / 'objects').rglob('*'):
        if obj.is_file(): obj.write_bytes(b'corrupt')
    result = cleanup_cache_plan(rt, 'test')
    assert source.exists()
    assert result['errors']


def test_cleanup_rejects_symlinked_ancestor_even_inside_root(tmp_path):
    rt, source, _ = setup_plan(tmp_path)
    moved = source.parent.with_name('moved-settings')
    source.parent.rename(moved)
    source.parent.symlink_to(moved, target_is_directory=True)
    result = cleanup_cache_plan(rt, 'test')
    assert (moved / 'raw.png').exists()
    assert result['errors']


def test_generated_settings_projection_is_not_treated_as_original_asset(tmp_path):
    rt, source, target = setup_plan(tmp_path, projection=True)
    projection = source.parent / 'series.json'
    result = cleanup_cache_plan(rt, 'test')
    assert result['errors'] == []
    assert projection.exists()  # Reconstructed config is not an original image.


def test_cleanup_never_deletes_untracked_file_with_same_content(tmp_path):
    rt, source, target = setup_plan(tmp_path, untracked=True)
    extra = source.parent / 'untracked-copy.png'
    result = cleanup_cache_plan(rt, 'test')
    assert extra.read_bytes() == b'original'
    assert not source.exists()
    assert result['errors'] == []
