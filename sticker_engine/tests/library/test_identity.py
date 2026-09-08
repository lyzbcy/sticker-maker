from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta


def test_platform_placeholder_hydrates_after_published_draft_uuid_arrives(tmp_path):
    a = LibraryRuntime(tmp_path / 'a'); a.bind('a@example.com', True)
    source = a.output_root / 'episode_generated'
    save_meta(source, EpisodeMeta(album_name='同一平台作品'))
    (source / 'raw.png').write_bytes(b'original')
    a.capture(source)
    metadata = load_meta(source)
    draft_id = metadata.work_id
    metadata.platform_item_id = 'platform1'
    save_meta(source, metadata); a.capture(source)

    b = LibraryRuntime(tmp_path / 'b'); b.bind('a@example.com', True)
    placeholder = b.placeholder({'StikerID': 'platform1', 'Name': '同一平台作品'})
    b.capture(placeholder)
    assert load_meta(placeholder).work_id != draft_id  # Truly distinct historical UUIDs.
    b.connect(a.library.root)
    rows = b.rows()
    assert len(rows) == 1
    assert rows[0]['resource_state'] == 'available'
    assert (b.path_for(rows[0]['work_id']) / 'raw.png').read_bytes() == b'original'
    b.refresh()
    assert len(b.rows()) == 1


def test_duplicate_resource_identity_is_a_conflict_card_and_clears_after_delete(tmp_path):
    rt = LibraryRuntime(tmp_path / 'device'); rt.bind('a@example.com', True)
    paths = []
    for index in ('one', 'two'):
        path = rt.output_root / ('episode_' + index)
        save_meta(path, EpisodeMeta(album_name=index))
        (path / 'raw.txt').write_text(index, encoding='utf-8')
        result = rt.capture(path)
        meta = load_meta(path)
        meta.platform_item_id = 'same-platform'
        save_meta(path, meta)
        rt.capture(path)
        paths.append((result['work_id'], path))

    rt.refresh()
    status = rt.status()
    cards = {item['work_id']: item for item in status['conflicts']}
    assert set(cards) == {work_id for work_id, _path in paths}
    assert all(card.get('heads') for card in cards.values())
    assert all(item['work_id'] not in {work_id for work_id, _path in paths}
               for item in status['deleted'])

    rt.delete(paths[1][0], 'delete')
    status = rt.status()
    assert not status['conflicts']
    assert any(item['work_id'] == paths[1][0] for item in status['deleted'])
