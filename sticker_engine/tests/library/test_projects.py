"""Portable projects must preserve publication identity and human work."""
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from sticker_engine.config.series import EpisodeMeta, load_meta, save_meta
from sticker_engine.library.runtime import LibraryRuntime, account_key, runtime_for_user_data
from sticker_engine.library.project_transfer import (preview_migration, execute_migration,
                                                    preview_slim, execute_slim)
from sticker_engine.project import (create_project, read_project, read_meanings,
                                    rename_project, seal_project, safe_file, require_sources)


@pytest.fixture
def old(tmp_path):
    rt = LibraryRuntime(tmp_path / 'device')
    rt.state.update(account_id=account_key('owner'), account_label='owner')
    rt.state['accounts'][rt.account_id] = 'owner'
    rt.state['library_id'] = rt.library.library_id
    rt.save()
    source = tmp_path / 'input'; source.mkdir()
    files = {}
    values = {'原图/grid.png': b'original', '原图/_noword/开心.png': b'no-word',
              'meaning_map.json': json.dumps({str(i):f'词{i}' for i in range(1,9)}).encode(),
              'rating.json': b'{"overall":92,"note":"human","ratings":{"word":{"score":88}}}',
              '介绍.txt': '正式介绍'.encode(), '本次制作角色.md': '角色：星星布丁'.encode()}
    for i in range(1,9):
        p = source / f'final{i}.png'; Image.new('RGBA', (240,240), (i,0,0,255)).save(p)
        values[f'最终版/词{i}.png'] = p.read_bytes()
    for logical in ('封面/封面.png','横幅/横幅.png','图标/图标.png',
                    '赞赏图/赞赏引导图.png','赞赏图/赞赏致谢图.png'):
        values[logical] = values['最终版/词1.png']
    for n,(logical,body) in enumerate(values.items()):
        p=source/f'{n}.data'; p.write_bytes(body)
        files[logical] = rt.library.put_file(p)
    meta = EpisodeMeta(work_id='stable-work', account_id=rt.account_id,
                       account_label='owner', album_name='周三涵做表情37',
                       created_at='2026-10-20 10:00:00',
                       intro='正式介绍', platform_item_id='platform-original', published=True)
    rt.library.write_revision(rt.account_id, meta.work_id, dict(meta.to_dict(),kind='episode'),files)
    target=tmp_path/'projects';target.mkdir()
    return rt,target,values


def convert(old):
    rt,target,_=old
    plan=preview_migration(rt,target)
    assert not plan['missing']
    execute_migration(rt,plan['plan_id'])
    direct=runtime_for_user_data(rt.user_data)
    return direct,target/'周三涵做表情37'


def test_location_parent_discovery_is_read_only(old):
    from sticker_engine.library.locations import inspect_location
    rt, _, _ = old
    root = rt.library.root
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    found = inspect_location(str(root.parent))['candidates']
    assert len(found) == 1
    assert found[0]['storage_mode'] == 'legacy'
    assert found[0]['accounts'] == [dict(account_id=rt.account_id, account_label='owner')]
    assert before == {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_location_new_machine_connects_legacy_and_remembers(old, tmp_path):
    from sticker_engine.library.locations import connect_location
    original, _, _ = old
    fresh = LibraryRuntime(tmp_path / 'fresh-device')
    result = connect_location(fresh, dict(path=str(original.library.root),
        library_id=original.library.library_id, account_id=original.account_id, confirm_account=True))
    assert result['connected'] and result['counts']['available'] == 1
    restarted = LibraryRuntime(fresh.user_data)
    assert restarted.account_id == original.account_id
    assert restarted.library.root == original.library.root
    assert restarted.rows()[0]['platform_item_id'] == 'platform-original'


def test_location_new_machine_direct_restart_without_workspaces(old, tmp_path):
    from sticker_engine.library.locations import inspect_location, connect_location
    direct, p = convert(old)
    fresh = LibraryRuntime(tmp_path / 'new-machine')
    candidate = inspect_location(str(p))['candidates'][0]
    assert candidate['storage_mode'] == 'projects'
    result = connect_location(fresh, dict(path=candidate['path'], library_id=candidate['library_id'],
        account_id=direct.account_id, confirm_account=True))
    assert result['storage_mode'] == 'projects'
    restarted = runtime_for_user_data(fresh.user_data)
    assert restarted.output_root == p.parent
    assert restarted.rows()[0]['platform_item_id'] == 'platform-original'
    assert not (fresh.user_data / 'resource_library/workspaces').exists()
    assert not (p.parent / '.sticker-maker-workspaces').exists()


def test_location_rejects_changed_identity_and_unconfirmed_account(old, tmp_path):
    from sticker_engine.library.locations import connect_location
    rt, _, _ = old
    fresh = LibraryRuntime(tmp_path / 'fresh')
    args = dict(path=str(rt.library.root), library_id=rt.library.library_id,
                account_id=rt.account_id, confirm_account=True)
    with pytest.raises(ValueError, match='确认'):
        connect_location(fresh, dict(args, confirm_account=False))
    with pytest.raises(ValueError, match='身份已变化'):
        connect_location(fresh, dict(args, library_id='different'))
    with pytest.raises(ValueError, match='库内的账号'):
        connect_location(fresh, dict(args, account_id='someone-else'))
    assert not fresh.config_file.exists()


def test_location_failed_connection_restores_previous_state(old, tmp_path, monkeypatch):
    from sticker_engine.library.locations import connect_location
    rt, _, _ = old
    fresh = LibraryRuntime(tmp_path / 'fresh')
    fresh.save()
    before = fresh.config_file.read_bytes()
    monkeypatch.setattr(LibraryRuntime, 'refresh', lambda *a, **kw: {'offline': True})
    with pytest.raises(ValueError, match='保留原连接'):
        connect_location(fresh, dict(path=str(rt.library.root), library_id=rt.library.library_id,
            account_id=rt.account_id, confirm_account=True))
    assert json.loads(fresh.config_file.read_bytes()) == json.loads(before)
    assert not runtime_for_user_data(fresh.user_data).account_id


def test_location_empty_folder_does_not_create_library(tmp_path):
    from sticker_engine.library.locations import inspect_location
    assert inspect_location(str(tmp_path)) == dict(candidates=[], errors=[])
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match='绝对路径'):
        inspect_location('')


def test_migration_direct_restart_and_no_object_or_workspace_copy(old):
    rt,p=convert(old)
    assert rt.__class__.__name__=='ProjectRuntime'
    assert rt.output_root==p.parent
    assert not (p.parent/'objects').exists()
    assert not (p.parent/'.sticker-maker-workspaces').exists()
    assert load_meta(p).platform_item_id=='platform-original'
    assert (p/'rating.json').read_bytes()==old[2]['rating.json']
    assert not (p/'meaning_map.json').exists()
    assert read_meanings(p)=={str(i):f'词{i}' for i in range(1,9)}
    assert rt.rows()[0]['can_publish']
    before=sorted(str(f.relative_to(p.parent)) for f in p.parent.rglob('*'))
    rt.refresh();rt.refresh();rt.rows()
    assert before==sorted(str(f.relative_to(p.parent)) for f in p.parent.rglob('*'))


def test_compact_preserves_exact_finals_ratings_and_publisher(old):
    from sticker_engine.publish.publisher import EpisodeAssets
    rt,p=convert(old)
    before=EpisodeAssets.from_dir(p)
    final_bytes={str(f.relative_to(p)):f.read_bytes() for f in before.stickers}
    plan=preview_slim(rt,[p],True)
    with pytest.raises(ValueError,match='确认'):
        execute_slim(rt,plan['plan_id'])
    execute_slim(rt,plan['plan_id'],True)
    assert read_project(p)['mode']=='delivery'
    assert not list((p/'原图').rglob('*.png'))
    assert (p/'rating.json').read_bytes()==old[2]['rating.json']
    after=EpisodeAssets.from_dir(p)
    assert before.meanings==after.meanings
    assert after.album_name=='周三涵做表情37'
    assert after.intro=='正式介绍'
    assert after.characters==['星星布丁']
    assert all((p/n).read_bytes()==b for n,b in final_bytes.items())
    assert rt.rows()[0]['can_publish']
    rt.refresh()
    assert not list((p/'原图').rglob('*.png'))
    with pytest.raises(ValueError,match='精简工程'):
        require_sources(p)


def test_cache_only_does_not_discard_sources(old):
    rt,p=convert(old)
    cache=p/'.cache'/'preview.png';cache.parent.mkdir();cache.write_bytes(b'cache')
    plan=preview_slim(rt,[p])
    assert plan['bytes']==5
    execute_slim(rt,plan['plan_id'])
    assert (p/'原图/grid.png').exists()
    assert read_project(p)['mode']=='full'
    assert not cache.exists()


def test_changed_final_blocks_source_deletion(old):
    rt,p=convert(old);plan=preview_slim(rt,[p],True)
    (p/'最终版/词1.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='变化'):
        execute_slim(rt,plan['plan_id'],True)
    assert (p/'原图/grid.png').exists()


def test_unsaved_edit_blocks_preview(old):
    rt,p=convert(old)
    (p/'原图/grid.png').write_bytes(b'edited')
    with pytest.raises(ValueError,match='未保存'):
        preview_slim(rt,[p],True)


def test_human_rating_edit_is_saved_without_copying_artwork(old):
    rt,p=convert(old);before=(p/'最终版/词1.png').stat().st_mtime_ns
    (p/'rating.json').write_text('{"overall":99}',encoding='utf-8')
    rt.capture(p)
    assert read_project(p)['files']['rating.json']['size']==14
    assert (p/'最终版/词1.png').stat().st_mtime_ns==before


def test_readable_rename_and_manual_move_keep_identity(old):
    rt,p=convert(old)
    m=load_meta(p);m.album_name='星星布丁第一弹';save_meta(p,m)
    new=rename_project(p,m.album_name)
    assert new.name=='星星布丁第一弹'
    assert rt.path_for(m.work_id)==new
    moved=new.with_name('星星布丁第一弹-手动整理');new.rename(moved)
    assert rt.path_for(m.work_id)==moved
    assert load_meta(moved).platform_item_id=='platform-original'


def test_name_collision_preserves_both_projects(old):
    rt,p=convert(old)
    dest=p.parent/'星星布丁第一弹';dest.mkdir()
    create_project(dest,EpisodeMeta(work_id='another',account_id=rt.account_id).to_dict())
    renamed=rename_project(p,'星星布丁第一弹')
    assert renamed.name=='星星布丁第一弹（副本2）'
    assert read_project(dest)['metadata']['work_id']=='another'


def test_unknown_and_custom_files_are_not_deleted(old):
    rt,p=convert(old)
    (p/'人工修改.psd').write_bytes(b'unique')
    seal_project(p)
    plan=preview_slim(rt,[p],True);execute_slim(rt,plan['plan_id'],True)
    assert (p/'人工修改.psd').read_bytes()==b'unique'


def test_unknown_submit_is_migrated_and_blocks_slim(old):
    from sticker_engine.library.operations import begin,unresolved
    old_rt=old[0];op=begin(old_rt,'stable-work','周三涵做表情37')
    rt,p=convert(old)
    assert unresolved(rt)[0]['operation_id']==op
    with pytest.raises(ValueError,match='待核对'):
        preview_slim(rt,[p],True)


def test_sync_conflict_blocks_edits(old):
    rt,p=convert(old)
    (p/'project.sync-conflict-peer.json').write_text('{}')
    with pytest.raises(ValueError,match='同步冲突'):
        save_meta(p,load_meta(p))


def test_manifest_rejects_escape(old):
    rt,p=convert(old)
    with pytest.raises(ValueError):
        safe_file(p,'../outside.png')


def test_existing_same_name_legacy_folder_not_overwritten(old):
    rt,target,_=old
    existing=target/'周三涵做表情37';existing.mkdir();(existing/'my.png').write_bytes(b'precious')
    plan=preview_migration(rt,target)
    assert Path(plan['entries'][0]['target']).name=='周三涵做表情37（副本2）'
    execute_migration(rt,plan['plan_id'])
    assert (existing/'my.png').read_bytes()==b'precious'


def test_partial_copy_restart_recovers_without_overwrite(old,monkeypatch):
    rt,target,_=old;plan=preview_migration(rt,target)
    actual=shutil.copy2;count=0
    def fail_once(a,b):
        nonlocal count
        count+=1
        if count==3:raise OSError('simulated interruption')
        return actual(a,b)
    monkeypatch.setattr(shutil,'copy2',fail_once)
    with pytest.raises(OSError):execute_migration(rt,plan['plan_id'])
    assert rt.state.get('storage_mode')!='projects'
    monkeypatch.setattr(shutil,'copy2',actual)
    execute_migration(rt,plan['plan_id'])
    assert load_meta(target/'周三涵做表情37').work_id=='stable-work'


def test_old_copies_freed_only_after_verification_and_history_retained(old):
    from sticker_engine.library.project_transfer import preview_old_copies, execute_old_copies
    old_rt,target,_ = old
    # This object is deliberately unreferenced; it must survive cleanup too.
    precious=old_rt.library.root/'unknown-note.txt';precious.write_bytes(b'historical note')
    root=old_rt.library.root
    rt,p=convert(old)
    plan=preview_old_copies(rt,rt.state['project_migration_id'])
    assert plan['estimated_freed_bytes']>0
    result=execute_old_copies(rt,plan['plan_id'])
    assert result['state']=='completed'
    assert not precious.exists()
    assert not list(root.rglob('*.json'))
    archive=p.parent/'.project-data/history'
    assert any(f.is_file() and f.read_bytes()==b'historical note' for f in archive.rglob('*'))
    assert (p/'原图/grid.png').read_bytes()==b'original'
    assert rt.rows()[0]['can_publish']


def test_source_change_after_cleanup_preview_retains_all_old_files(old):
    from sticker_engine.library.project_transfer import preview_old_copies, execute_old_copies
    rt,p=convert(old);source=Path(old[0].state['root']) if old[0].state.get('root') else old[0].local/'library'
    plan=preview_old_copies(rt,rt.state['project_migration_id'])
    original_count=len([f for f in source.rglob('*') if f.is_file()])
    item=plan['entries'][-1];Path(item['source']).write_bytes(b'changed after preview')
    with pytest.raises(ValueError,match='变化'):
        execute_old_copies(rt,plan['plan_id'])
    assert len([f for f in source.rglob('*') if f.is_file()])==original_count


@pytest.mark.parametrize('n,text',[(1,'第一弹'),(10,'第十弹'),(11,'第十一弹'),(20,'第二十弹'),(101,'第一百零一弹')])
def test_xingxing_series_keeps_chinese_names(n,text):
    from sticker_engine.config.series import Series
    assert Series(id='star',name='星星布丁').album_name(n)=='星星布丁'+text


def test_direct_api_generation_never_calls_legacy_settings_capture(old,monkeypatch):
    from types import SimpleNamespace
    from sticker_engine.api import StickerEngine,Episode
    from sticker_engine.library.settings import SharedSettings
    rt,p=convert(old)
    engine=StickerEngine(SimpleNamespace(paths=SimpleNamespace(user_data=rt.user_data)))
    def generate(**kwargs):
        return Episode(episode_dir=p)
    monkeypatch.setattr(engine,'_run_impl',generate)
    monkeypatch.setattr(SharedSettings,'capture',lambda *_: (_ for _ in ()).throw(AssertionError('legacy capture invoked')))
    result=engine.run()
    assert result.success,result.aborted_reason


def test_cli_rating_save_reseals_only_selected_project(old,monkeypatch):
    from types import SimpleNamespace
    from sticker_engine.library import hooks
    rt,p=convert(old)
    cli=SimpleNamespace(_ensure_engine=lambda:SimpleNamespace(config=SimpleNamespace(paths=SimpleNamespace(user_data=rt.user_data))))
    def save(_id,_args):
        (p/'rating.json').write_bytes(b'{"overall":97}')
    hooks.invoke(cli,'rating','save_rating',{'episode_dir':str(p)},save)
    plan=preview_slim(rt,[p],True)
    execute_slim(rt,plan['plan_id'],True)
    assert json.loads((p/'rating.json').read_text())['overall']==97


def test_compact_project_can_still_save_rating_without_restoring_sources(old):
    rt,p=convert(old)
    plan=preview_slim(rt,[p],True);execute_slim(rt,plan['plan_id'],True)
    (p/'rating.json').write_text('{"overall":81}',encoding='utf-8')
    rt.capture(p)
    assert read_project(p)['mode']=='delivery'
    assert not list((p/'原图').rglob('*.png'))


def test_real_pipeline_mock_provider_names_new_project_and_relocates_stickers(old,monkeypatch):
    from sticker_engine import StickerEngine,Config
    from sticker_engine.config.paths import resolve_paths,current_platform
    from sticker_engine.config.series import Series,save_series
    rt,p=convert(old)
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA',str(rt.user_data))
    config=Config.placeholder();config.paths=resolve_paths(current_platform())
    config.prefs.default_series_id='star'
    save_series([Series(id='star',name='星星布丁')])
    engine=StickerEngine(config);engine._inject_test_mocks()
    episode=engine.run()
    assert episode.success,episode.aborted_reason
    assert episode.episode_dir.name=='星星布丁第一弹'
    assert len(episode.stickers)==16
    assert all(s.path.is_file() and s.path.is_relative_to(episode.episode_dir) for s in episode.stickers)
    assert (episode.episode_dir/'.cache/panels').is_dir()
    assert not (episode.episode_dir/'原图/_panels').exists()
    assert read_project(episode.episode_dir)['meaning_map']
    assert not (episode.episode_dir/'meaning_map.json').exists()


def test_normalize_flat_xingxing_and_existing_zhou_without_copying(old):
    from sticker_engine.library.project_transfer import preview_normalize,execute_normalize
    rt,p=convert(old)
    star=p.parent/'星星布丁第二弹';star.mkdir()
    (star/'抱抱.png').write_bytes(old[2]['最终版/词1.png'])
    (star/'收到.gif').write_bytes(b'gif-content')
    (star/'notes.txt').write_bytes(b'handmade')
    zhou=p.parent/'周三涵做表情38';zhou.mkdir()
    (zhou/'最终版').mkdir();(zhou/'最终版/好.png').write_bytes(old[2]['最终版/词1.png'])
    plan=preview_normalize(rt)
    assert len(plan['entries'])==2 and not plan['missing']
    execute_normalize(rt,plan['plan_id'])
    assert (star/'最终版/抱抱.png').read_bytes()==old[2]['最终版/词1.png']
    assert (star/'最终版/收到.gif').read_bytes()==b'gif-content'
    assert (star/'notes.txt').read_bytes()==b'handmade'
    assert load_meta(star).album_name==star.name
    assert load_meta(zhou).album_name==zhou.name
    assert len(rt.rows())==3


def test_differing_diagnostic_is_preserved_alongside_library_version(old):
    rt,target,_=old
    work=rt.library.read_work(rt.account_id,'stable-work');rev=work['revision']
    screenshot=target.parent/'library-error.png';screenshot.write_bytes(b'library diagnostic')
    files=dict(rev['files']);files['_publish_error.png']=rt.library.put_file(screenshot)
    rt.library.write_revision(rt.account_id,'stable-work',rev['metadata'],files)
    source=rt.output_root/'episode_local';source.mkdir(parents=True)
    save_meta(source,EpisodeMeta.from_dict(rev['metadata']))
    (source/'_publish_error.png').write_bytes(b'local diagnostic')
    plan=preview_migration(rt,target)
    assert not plan['missing']
    execute_migration(rt,plan['plan_id'])
    p=target/'周三涵做表情37'
    assert (p/'_publish_error.png').read_bytes()==b'library diagnostic'
    assert next((p/'诊断记录').iterdir()).read_bytes()==b'local diagnostic'


def test_new_work_arriving_after_preview_blocks_activation(old):
    rt,target,_=old;plan=preview_migration(rt,target)
    meta=EpisodeMeta(work_id='new-peer-work',account_id=rt.account_id,album_name='新来的工程')
    rt.library.write_revision(rt.account_id,meta.work_id,dict(meta.to_dict(),kind='episode'),{})
    with pytest.raises(ValueError,match='新增或修改'):
        execute_migration(rt,plan['plan_id'])
    assert rt.state.get('storage_mode')!='projects'
    assert not (target/'projects.json').exists()
