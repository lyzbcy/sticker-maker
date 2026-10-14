import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.library.reconciliation import choose_preserving_ratings
from sticker_engine.library.runtime import LibraryRuntime
from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta


def variants(tmp_path):
    lib = ResourceLibrary(tmp_path / 'lib', create=True)
    p = tmp_path / 'art.png'; p.write_bytes(b'old-art')
    meta = {'kind': 'episode', 'album_name': '作品', 'platform_item_id': '1'}
    old = {'最终版/睡了.png': lib.put_file(p)}
    root = lib.write_revision('a', 'w', meta, old, parents=[])
    p = tmp_path / 'rating.json'
    document = {'rated_at': '2026-09-01', 'production': {'prompt_file_content': 'original prompt'},
                'overall': 3, 'ratings': {'睡了': {'score': 1, 'note': '切掉了脸'}}}
    p.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    ref = lib.put_file(p)
    a = lib.write_revision('a', 'w', meta, dict(old, **{'rating.json': ref}), parents=[root['revision_id']])
    p = tmp_path / 'new.png'; p.write_bytes(b'complete-new-art')
    b = lib.write_revision('a', 'w', meta, {'最终版/睡了.png': lib.put_file(p)}, parents=[root['revision_id']])
    return lib, a, b, document


def read_object(lib, ref):
    d = ref['sha256']; return (lib.root / 'objects' / d[:2] / d).read_bytes()


def test_explicit_choice_retains_exact_rating_and_original_context(tmp_path):
    lib, a, b, document = variants(tmp_path)
    before = copy.deepcopy(lib.revisions('a', 'w'))
    merged = choose_preserving_ratings(lib, 'a', 'w', b['revision_id'], [a['revision_id'], b['revision_id']])
    assert merged['files']['最终版/睡了.png'] == b['files']['最终版/睡了.png']
    assert merged['files']['rating.json'] == a['files']['rating.json']
    assert json.loads(read_object(lib, merged['files']['rating.json'])) == document
    assert merged['files'][f"_rating_history/{a['revision_id']}/rating.json"] == a['files']['rating.json']
    prov = json.loads(read_object(lib, merged['files']['rating_provenance.json']))
    assert prov['inherited_from_other_artwork'] is True
    assert prov['sources'][0]['files'] == a['files']
    assert prov['sources'][0]['changed_or_removed_final_paths'] == ['最终版/睡了.png']
    assert set(merged['parents']) == {a['revision_id'], b['revision_id']}
    assert all(r in lib.revisions('a', 'w') for r in before)


def test_stale_preview_leaves_all_heads_intact(tmp_path):
    lib, a, b, _ = variants(tmp_path)
    with pytest.raises(ValueError, match='版本头'):
        choose_preserving_ratings(lib, 'a', 'w', b['revision_id'], [b['revision_id']])
    assert lib.read_work('a', 'w')['state'] == 'conflict'


def test_multiple_different_human_ratings_require_choice(tmp_path):
    lib, a, b, doc = variants(tmp_path)
    doc['ratings']['睡了']['score'] = 5
    p = tmp_path / 'other-rating.json'; p.write_text(json.dumps(doc), encoding='utf-8')
    b = lib.write_revision('a', 'w', b['metadata'], dict(b['files'], **{'rating.json': lib.put_file(p)}), parents=[b['revision_id']])
    with pytest.raises(ValueError, match='不同人工评分'):
        choose_preserving_ratings(lib, 'a', 'w', b['revision_id'], [a['revision_id'], b['revision_id']])


def test_different_platform_identity_blocks_rating_choice(tmp_path):
    lib, a, b, _ = variants(tmp_path)
    b = lib.write_revision('a', 'w', dict(b['metadata'], platform_item_id='other'), b['files'], parents=[b['revision_id']])
    with pytest.raises(ValueError, match='身份不同'):
        choose_preserving_ratings(lib, 'a', 'w', b['revision_id'], [a['revision_id'], b['revision_id']])


def test_actual_projection_changes_not_just_marker_and_cross_device_receives_it(tmp_path):
    rt = LibraryRuntime(tmp_path / 'device-a'); rt.bind('a@example.com', True)
    path = rt.output_root / 'episode_old'
    save_meta(path, EpisodeMeta(album_name='作品', platform_item_id='1'))
    (path / '最终版').mkdir(); (path / '最终版/睡了.png').write_bytes(b'old')
    (path / 'rating.json').write_text('{"ratings":{"睡了":{"score":1}}}', encoding='utf-8')
    initial = rt.capture(path); wid = initial['work_id']
    a = rt.library.read_work(rt.account_id, wid)['revision']
    p = tmp_path / 'new.png'; p.write_bytes(b'new-complete')
    b = rt.library.write_revision(rt.account_id, wid, a['metadata'],
         {'最终版/睡了.png': rt.library.put_file(p)}, parents=[])
    # Migration leaves historical markers outside the active workspace.
    legacy=tmp_path/'old-migration'/'episode_old';legacy.mkdir(parents=True)
    (legacy/'untouched.txt').write_text('historical',encoding='utf-8')
    rt.state['paths'][str(legacy)] = copy.deepcopy(rt.state['paths'][str(path)])
    rt.resolve(wid, b['revision_id'], 'choose_keep_ratings', [a['revision_id'], b['revision_id']])
    assert (legacy/'untouched.txt').read_text(encoding='utf-8')=='historical'
    assert (path / '最终版/睡了.png').read_bytes() == b'new-complete'
    assert json.loads((path / 'rating.json').read_text(encoding='utf-8'))['ratings']['睡了']['score'] == 1
    rt.refresh()
    assert rt.library.read_work(rt.account_id, wid)['state'] == 'available'
    other = LibraryRuntime(tmp_path / 'device-b'); other.bind('a@example.com', True)
    other.connect(rt.library.root)
    rows = other.rows(); projected = next(x for x in rows if x['work_id'] == wid)
    assert ( __import__('pathlib').Path(projected['path']) / '最终版/睡了.png').read_bytes() == b'new-complete'
    assert other.status()['counts']['conflict'] == 0


def test_interrupted_materialization_resumes_after_marker_advanced(tmp_path):
    rt=LibraryRuntime(tmp_path/'device');rt.bind('a@example.com',True)
    p=rt.output_root/'episode_old';save_meta(p,EpisodeMeta(album_name='作品'))
    (p/'art.png').write_bytes(b'old');initial=rt.capture(p);wid=initial['work_id']
    a=rt.library.read_work(rt.account_id,wid)['revision']
    new=tmp_path/'new.png';new.write_bytes(b'new')
    b=rt.library.write_revision(rt.account_id,wid,a['metadata'],{'art.png':rt.library.put_file(new)},parents=[a['revision_id']])
    # Simulate the interrupted old resolve path advancing only its marker.
    rt.state['paths'][str(p)]['revision_id']=b['revision_id'];rt.save()
    assert rt.state['paths'][str(p)]['revision_id']==b['revision_id']
    assert (p/'art.png').read_bytes()==b'old'
    rt.materialize_chosen(wid,b['revision_id'])
    assert (p/'art.png').read_bytes()==b'new'
    assert rt.library.read_work(rt.account_id,wid)['revision']['revision_id']==b['revision_id']


def test_internal_operations_excluded_from_album_counts(tmp_path):
    rt = LibraryRuntime(tmp_path / 'device'); rt.bind('a@example.com', True)
    rt.library.write_revision(rt.account_id, 'album', {'kind':'episode'}, {}, parents=[])
    rt.library.write_revision(rt.account_id, 'operation', {'kind':'operation'}, {}, parents=[])
    rt.library.write_revision(rt.account_id, 'deleted-operation', {'kind':'operation'}, {}, parents=[], deleted=True)
    result = rt.status()
    assert sum(result['counts'].values()) == 1
    assert result['counts']['deleted'] == 0
    assert result['deleted'] == []


def test_partial_new_rating_keeps_unchanged_old_score_provenance(tmp_path, monkeypatch):
    from sticker_engine import cli
    save_meta(tmp_path, EpisodeMeta(album_name='作品'))
    old = {'overall': 3, 'ratings': {'睡了': {'score': 1}, '开心': {'score': 4}}}
    f = tmp_path/'rating.json'; f.write_text(json.dumps(old), encoding='utf-8')
    prov = {'inherited_from_other_artwork': True, 'rating_sha256': hashlib.sha256(f.read_bytes()).hexdigest()}
    (tmp_path/'rating_provenance.json').write_text(json.dumps(prov), encoding='utf-8')
    monkeypatch.setattr(cli, '_ensure_engine', lambda: SimpleNamespace())
    receipts=[]; monkeypatch.setattr(cli, '_result', lambda *a, **kw: receipts.append(kw))
    cli.cmd_save_rating('r', {'episode_dir': str(tmp_path), 'overall':3,
                            'ratings': {'睡了': {'score': 5}, '开心': {'score': 4}}})
    data=json.loads(f.read_text(encoding='utf-8'))
    assert data['inherited_rating_meanings'] == ['开心'] and data['inherited_overall'] is True
    cli.cmd_get_rating('r', {'episode_dir': str(tmp_path)})
    assert receipts[-1]['data']['provenance']['inherited_from_other_artwork'] is True
    (tmp_path/'rating_provenance.json').write_text('damaged', encoding='utf-8')
    cli.cmd_get_rating('r', {'episode_dir': str(tmp_path)})
    assert receipts[-1]['data']['ratings']['睡了']['score']==5
