"""Previewed, resumable conversion to named projects and opt-in source removal."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from ..project import (ASSET_DIRS, SOURCE_DIRS, atomic_json, create_project,
                       named_destination, read_characters, read_meanings, read_project,
                       safe_file, seal_project, update_project, project_lock)
from .resources import hash_file
from .runtime import read_json, LibraryRuntime


def _plan_path(runtime, plan_id):
    from .resources import validate_identifier
    validate_identifier(plan_id)
    return runtime.local / 'project_plans' / (plan_id + '.json')


def _emit(progress, completed, total, message):
    if progress:
        progress(dict(completed=completed, total=total, message=message))


def _catalog_signature(works):
    values=sorted((w['account_id'],w['work_id'],w['state'],
                   tuple(sorted(r['revision_id'] for r in w.get('heads',[])))) for w in works)
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()


def _check_migration_sources(runtime,plan):
    if not plan.get('source_signature'):
        raise ValueError('旧版预览已失效，请重新生成迁移预览')
    if _catalog_signature(runtime.library.list_works())!=plan['source_signature']:
        raise ValueError('旧库在预览后新增或修改了作品，请暂停其他设备后重新预览')
    for entry in plan['entries']:
        for check in entry.get('projection_checks',[]):
            if hash_file(Path(check['source']))!=(check['sha256'],check['size']):
                raise ValueError('本机工程在预览后发生变化，请重新预览')
    for source,expected in plan.get('projection_listings',{}).items():
        if sorted(str(p.relative_to(source)) for p in Path(source).rglob('*') if p.is_file())!=expected:
            raise ValueError('本机工程新增或删除了文件，请重新预览')


def preview_migration(runtime, target, progress=None):
    if runtime.state.get('storage_mode') == 'projects':
        raise ValueError('当前已经是规范工程模式')
    runtime.require_account()
    destination = Path(target).expanduser().resolve()
    if not str(target).strip() or not destination.is_dir() or destination.is_symlink():
        raise ValueError('请选择现有的工程根目录')
    lib = runtime.library
    if destination == lib.root or destination.is_relative_to(lib.root):
        raise ValueError('工程根目录不能放在旧资源库内部')
    if (destination / 'projects.json').exists():
        raise ValueError('目标已是工程集合，请直接连接或选择其他位置')
    _emit(progress,0,0,'正在读取旧库版本清单并校验对象；大量历史修订可能需要几分钟')
    works = lib.list_works()
    from ..project import episode_directories
    known_sources = {}
    for source in episode_directories(runtime.output_root):
        from ..config.series import load_meta
        identity = load_meta(source).work_id
        if identity:
            known_sources.setdefault(identity,[]).append(source)
    plan = dict(plan_id=uuid.uuid4().hex, kind='project_migration',
                source=str(lib.root), target=str(destination),
                source_workspace=str(runtime.output_root.parent),
                source_signature=_catalog_signature(works),projection_listings={},
                library_id=lib.library_id, account_id=runtime.account_id,
                entries=[], records=[], settings=[], missing=[], bytes=0, state='preview',
                # This conversion does not implicitly discard old history or drafts.
                source_cleanup=False)
    reserved = []
    for index, work in enumerate(works):
        rev = work.get('revision')
        if not rev or work['state'] in ('pending', 'conflict') or work.get('sync_conflicts'):
            plan['missing'].append(dict(work_id=work['work_id'], reason='资源未齐或存在冲突'))
            continue
        meta = copy.deepcopy(rev['metadata'])
        if meta.get('kind', 'episode') != 'episode':
            # Keep durable intent/unknown records (and settings metadata) intact.
            plan['records'].append(rev)
            continue
        # Preserve deleted projects as deleted; never silently resurrect them.
        name = meta.get('album_name') or meta.get('legacy_name') or '未命名表情'
        dest = named_destination(destination, name, work['work_id'], reserved)
        reserved.append(dest)
        entry = dict(work_id=work['work_id'], account_id=work['account_id'],
                     metadata=dict(meta, work_id=work['work_id'], account_id=work['account_id']),
                     revision_id=rev['revision_id'], deleted=bool(rev.get('deleted')),
                     target=str(dest), files=[], meaning_map={}, characters=[], projection_checks=[])
        for logical, ref in rev['files'].items():
            safe_file(dest, logical)
            src = lib.root / 'objects' / ref['sha256'][:2] / ref['sha256']
            if not src.is_file() or hash_file(src) != (ref['sha256'], ref['size']):
                plan['missing'].append(dict(work_id=work['work_id'], path=logical, reason='源对象缺失或校验失败'))
                continue
            if logical == 'meaning_map.json':
                entry['meaning_map'] = json.loads(src.read_text(encoding='utf-8'))
                continue
            if logical == '本次制作角色.md':
                for line in src.read_text(encoding='utf-8').splitlines():
                    if line.startswith('角色：'):
                        entry['characters'] = [c for c in line[3:].split('、') if c]
                continue
            if logical in ('meta.json', 'project.json', '介绍.txt'):
                continue
            entry['files'].append(dict(logical=logical, source=str(src), **ref))
            plan['bytes'] += ref['size']
        # Inspect every known projection, including unsaved local ratings.
        sources = [Path(p) for p, marker in runtime.state.get('paths', {}).items()
                   if marker.get('work_id') == work['work_id'] and Path(p).is_dir()]
        sources += known_sources.get(work['work_id'],[])
        # Legacy installations may have no device.json on this machine.
        # Discover portable projections by the embedded work_id, never by name.
        if hasattr(runtime, '_migration_sources'):
            sources += runtime._migration_sources.get(work['work_id'], [])
        local_ratings = {}
        for source in set(sources):
            from ..config.series import load_meta
            from .reconciliation import authored_metadata
            local_meta = load_meta(source)
            plan['projection_listings'][str(source)]=sorted(str(p.relative_to(source)) for p in source.rglob('*') if p.is_file())
            meta_file = source/'meta.json'
            if meta_file.is_file():
                sha,size=hash_file(meta_file)
                entry['projection_checks'].append(dict(source=str(meta_file),sha256=sha,size=size))
            authored = authored_metadata(local_meta.to_dict())
            library_meta = authored_metadata(meta)
            ignore = {'kind', 'legacy_name', 'missing_resources', 'alias_of', 'identity_alias'}
            if any(v != library_meta.get(k) for k, v in authored.items()
                   if k not in ignore and k not in ('cover_custom', 'banner_custom', 'icon_custom')):
                plan['missing'].append(dict(work_id=work['work_id'], path=str(source), reason='本机元数据与库不同，请先保存或处理分歧'))
            for p in source.rglob('*'):
                if not p.is_file():
                    continue
                logical = p.relative_to(source).as_posix()
                if logical in ('meta.json', '.project.lock') or logical.startswith('.cache/'):
                    continue
                sha, size = hash_file(p)
                entry['projection_checks'].append(dict(source=str(p),sha256=sha,size=size))
                if logical == 'rating.json':
                    local_ratings[sha] = dict(logical=logical, source=str(p), sha256=sha, size=size)
                elif logical in rev['files'] and rev['files'][logical] != dict(sha256=sha, size=size):
                    if logical in ('_publish_error.png','_before_submit.png') or logical.startswith('_diagnostics/'):
                        # Both diagnostics survive; no need to ask an artist
                        # to choose which historical failure screenshot to lose.
                        alias='诊断记录/'+p.stem+'-'+sha[:12]+p.suffix
                        if not any(f['logical']==alias for f in entry['files']):
                            entry['files'].append(dict(logical=alias,source=str(p),sha256=sha,size=size))
                            plan['bytes']+=size
                    else:
                        plan['missing'].append(dict(work_id=work['work_id'], path=str(p), reason='本机素材与库不同，保留原件并停止迁移'))
                elif logical not in rev['files'] and logical not in ('project.json',):
                    plan['missing'].append(dict(work_id=work['work_id'], path=str(p), reason='发现未入库文件，需先保存'))
        if len(local_ratings) > 1:
            plan['missing'].append(dict(work_id=work['work_id'], reason='多个副本人工评分不同，不能自动选取'))
        elif local_ratings:
            rating = next(iter(local_ratings.values()))
            old = next((i for i in entry['files'] if i['logical'] == 'rating.json'), None)
            if old:
                entry['files'].remove(old); plan['bytes'] -= old['size']
            entry['files'].append(rating); plan['bytes'] += rating['size']
        plan['entries'].append(entry)
        if index % 10 == 0:
            _emit(progress, index + 1, len(works), f'已检查 {index+1} 个工程/记录')
    # Shared settings are copied once; unlike episodes they are not duplicated
    # into a working cache. Capture exact bytes and preserve custom base images.
    from .settings import settings_dir
    settings_root = settings_dir(runtime)
    if settings_root.is_dir():
        for p in settings_root.rglob('*'):
            if p.is_file():
                sha, size = hash_file(p)
                plan['settings'].append(dict(source=str(p), logical=p.relative_to(settings_root).as_posix(),
                                              sha256=sha, size=size))
    atomic_json(_plan_path(runtime, plan['plan_id']), plan)
    return plan


def execute_migration(runtime, plan_id, progress=None):
    plan = read_json(_plan_path(runtime, plan_id))
    if plan.get('kind') != 'project_migration' or plan['missing']:
        raise ValueError('预览仍有缺失或分歧，请处理后重新预览')
    if runtime.account_id != plan['account_id'] or str(runtime.library.root) != plan['source']:
        raise ValueError('迁移来源或账号已变化')
    _check_migration_sources(runtime,plan)
    root = Path(plan['target'])
    if not root.is_dir() or root.is_symlink():
        raise ValueError('目标目录已变化')
    # Whole-plan preflight before first write. Preview is a frozen contract.
    for entry in plan['entries']:
        work = runtime.library.read_work(entry['account_id'], entry['work_id'])
        if (work.get('revision') or {}).get('revision_id') != entry['revision_id']:
            raise ValueError('源工程已变化，请重新预览')
        for f in entry['files']:
            if hash_file(Path(f['source'])) != (f['sha256'], f['size']):
                raise ValueError('源文件已变化，请重新预览')
        for f in entry.get('projection_checks',[]):
            if hash_file(Path(f['source'])) != (f['sha256'],f['size']):
                raise ValueError('本机工程在预览后发生变化，请重新预览')
    for i, entry in enumerate(plan['entries']):
        dest = Path(entry['target'])
        if dest.parent != root:
            raise ValueError('迁移目标越界')
        if dest.exists():
            existing = read_project(dest)
            if not existing or existing.get('migration_plan_id') != plan_id:
                raise ValueError('目标出现其他文件，已停止并保留全部内容')
            if existing.get('migration_complete'):
                for logical, ref in existing['files'].items():
                    if hash_file(safe_file(dest, logical)) != (ref['sha256'], ref['size']):
                        raise ValueError('已复制工程被修改，已停止')
                continue
        else:
            dest.mkdir(exist_ok=False)
            create_project(dest, entry['metadata'], meanings=entry['meaning_map'], characters=entry['characters'])
            update_project(dest, lambda d: d.update(migration_plan_id=plan_id))
        for f in entry['files']:
            target = safe_file(dest, f['logical'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if hash_file(target) != (f['sha256'], f['size']):
                    raise ValueError('目标文件不同，拒绝覆盖')
            else:
                temp = target.with_name('.' + target.name + '.copying')
                if temp.is_symlink():
                    raise ValueError('目标临时路径是链接')
                shutil.copy2(f['source'], temp)
                if hash_file(temp) != (f['sha256'], f['size']):
                    raise ValueError('复制后校验失败')
                temp.replace(target)
        seal_project(dest)
        update_project(dest, lambda d: d.update(deleted=entry['deleted'], migration_complete=True))
        _emit(progress, i+1, len(plan['entries']), f'已转换 {i+1}/{len(plan["entries"])} 个工程')
    records_root = root / '.project-data' / 'records'
    for rev in plan['records']:
        atomic_json(records_root / rev['account_id'] / (rev['work_id'] + '.json'), rev)
    for item in plan['settings']:
        if hash_file(Path(item['source'])) != (item['sha256'], item['size']):
            raise ValueError('设置已变化，请重新预览')
        target = safe_file(root / '.project-data' / 'settings' / runtime.account_id, item['logical'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item['source'], target)
    # Replace machine-specific settings paths with portable paths before the
    # old workspace can be retired. Credentials are deliberately not migrated.
    settings_dest = root / '.project-data' / 'settings' / runtime.account_id
    prefs = settings_dest/'prefs.yaml'
    if prefs.is_file():
        import yaml
        data=yaml.safe_load(prefs.read_text(encoding='utf-8')) or {}
        data['reference_lib_path']='reference_library'
        prefs.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8')
    # A peer can add an entirely new work while bytes are being copied. Check
    # the whole catalog again, not just the works listed in the original plan.
    _check_migration_sources(runtime,plan)
    atomic_json(root / 'projects.json', dict(format='sticker-maker-project-collection', schema_version=1,
                library_id=plan['library_id']))
    previous = copy.deepcopy(runtime.state)
    atomic_json(runtime.local / 'project_plans' / (plan_id + '-previous-device.json'), previous)
    runtime.state.update(storage_mode='projects', project_root=str(root), paths={}, last_rows=[],
                         project_migration_id=plan_id)
    runtime.state.pop('workspace_base', None)
    runtime.save()
    plan.update(state='completed', message='工程已转换并切换；旧库和工作副本暂保留，尚未释放源空间')
    atomic_json(_plan_path(runtime, plan_id), plan)
    return plan


def preview_slim(runtime, paths, delete_sources=False):
    if runtime.state.get('storage_mode') != 'projects':
        raise ValueError('请先迁移为规范工程')
    from .operations import unresolved
    busy = {op['work_id'] for op in unresolved(runtime)}
    plan = dict(plan_id=uuid.uuid4().hex, kind='project_slim', root=str(runtime.output_root),
                account_id=runtime.account_id, delete_sources=bool(delete_sources), entries=[], bytes=0,
                state='preview')
    if not paths:
        raise ValueError('请选择至少一个工程')
    for raw in paths:
        path = Path(raw).resolve()
        if path.parent != runtime.output_root:
            raise ValueError('只能瘦身当前工程目录内的作品')
        data = read_project(path)
        if not data or data['metadata'].get('account_id') != runtime.account_id:
            raise ValueError('不是当前账号的规范工程')
        if data['metadata']['work_id'] in busy or data['metadata'].get('resource_placeholder'):
            raise ValueError('存在待核对投稿或素材不完整，不能瘦身')
        # Validate *all* retained files too; a broken final is never a reason to
        # destroy the only remaining source image.
        for logical, ref in data['files'].items():
            if hash_file(safe_file(path, logical)) != (ref['sha256'], ref['size']):
                raise ValueError('工程有未保存修改或缺失文件，请先保存后重新预览')
        if not list((path / '最终版').glob('*.png')):
            raise ValueError('工程没有最终表情，不能瘦身')
        removals = []
        for p in path.rglob('*'):
            if not p.is_file():
                continue
            rel = p.relative_to(path).as_posix()
            first = rel.split('/')[0]
            # Unknown files remain untouched. Only classified source files and
            # cache files qualify, never arbitrary images found by extension.
            sources = set(data.get('source_directories') or SOURCE_DIRS) | SOURCE_DIRS
            if first == '.cache' or (delete_sources and first in sources):
                sha, size = hash_file(safe_file(path, rel))
                removals.append(dict(logical=rel, sha256=sha, size=size))
                plan['bytes'] += size
        plan['entries'].append(dict(path=str(path), revision_id=data['revision_id'], files=removals))
    atomic_json(_plan_path(runtime, plan['plan_id']), plan)
    return plan


def execute_slim(runtime, plan_id, confirm_discard_sources=False):
    plan = read_json(_plan_path(runtime, plan_id))
    if (plan.get('kind') != 'project_slim' or runtime.account_id != plan['account_id']
            or str(runtime.output_root) != plan['root']):
        raise ValueError('瘦身预览与当前工程目录不一致')
    if plan['delete_sources'] and not confirm_discard_sources:
        raise ValueError('删除原图需要明确确认不可恢复影响')
    from .operations import unresolved
    busy = {op['work_id'] for op in unresolved(runtime)}
    # Revalidate all projects BEFORE destroying any source bytes.
    for entry in plan['entries']:
        p = Path(entry['path'])
        data = read_project(p)
        if (p.parent != runtime.output_root or data['revision_id'] != entry['revision_id']
                or data['metadata']['work_id'] in busy):
            raise ValueError('工程或投稿状态已变化，请重新预览')
        for logical, ref in data['files'].items():
            if hash_file(safe_file(p, logical)) != (ref['sha256'], ref['size']):
                raise ValueError('工程文件已变化，请重新预览')
        for item in entry['files']:
            if hash_file(safe_file(p, item['logical'])) != (item['sha256'], item['size']):
                raise ValueError('候选文件已变化，请重新预览')
    cleaned = 0
    for entry in plan['entries']:
        p = Path(entry['path'])
        removed = {f['logical'] for f in entry['files']}
        def change(data):
            data['files'] = {k:v for k,v in data['files'].items() if k not in removed}
            if plan['delete_sources']:
                data['mode'] = 'delivery'
            data['cleanup_pending'] = entry['files']
        with project_lock(p):
            update_project(p, change, entry['revision_id'])
            # Mark mode first; keep the project lock through deletion so a
            # simultaneous rating save cannot re-adopt the pending raw files.
            resume_cleanup(p)
        cleaned += sum(f['size'] for f in entry['files'])
    plan.update(state='completed', freed_bytes=cleaned)
    atomic_json(_plan_path(runtime, plan_id), plan)
    return plan


def resume_cleanup(directory):
    data = read_project(directory)
    for item in data.get('cleanup_pending', []):
        p = safe_file(directory, item['logical'])
        if not p.exists():
            continue
        if hash_file(p) != (item['sha256'], item['size']):
            raise ValueError('待清理文件被修改，已保留，请检查后重新预览')
        p.unlink()
    if data.get('cleanup_pending'):
        update_project(directory, lambda d: d.pop('cleanup_pending', None))


def preview_old_copies(runtime, migration_id, progress=None):
    """All original bytes must have a verified destination before old copies go.

    Unique history/unsaved metadata is retained in a small history store, rather
    than throwing away old revisions to achieve an inflated savings estimate.
    """
    migration = read_json(_plan_path(runtime, migration_id))
    if (runtime.state.get('storage_mode') != 'projects' or migration.get('state') != 'completed'
            or str(runtime.output_root) != migration['target']):
        raise ValueError('需要已完成并激活的工程转换记录')
    roots = [Path(migration['source']), Path(migration['source_workspace'])]
    from .catalog import ResourceLibrary
    if _catalog_signature(ResourceLibrary(roots[0]).list_works())!=migration.get('source_signature'):
        raise ValueError('旧库在转换后又有变化，已保留旧副本；请先核对其他设备的新作品')
    if any(r == runtime.output_root or runtime.output_root.is_relative_to(r) for r in roots):
        raise ValueError('旧副本路径包含当前工程目录，不能清理')
    targets = {}
    from ..project import project_directories
    for p in project_directories(runtime.output_root):
        project = read_project(p)
        for logical, ref in project['files'].items():
            f = safe_file(p, logical)
            if hash_file(f) != (ref['sha256'], ref['size']):
                raise ValueError('新工程尚有变化或缺失，请先保存后再清理旧副本')
            targets[ref['sha256']] = str(f)
    plan = dict(plan_id=uuid.uuid4().hex, kind='project_old_copies',
                root=str(runtime.output_root), account_id=runtime.account_id,
                roots=[str(r) for r in roots], migration_id=migration_id,
                source_signature=migration['source_signature'],
                entries=[], bytes=0, history_bytes=0, state='preview')
    archive = runtime.output_root / '.project-data' / 'history' / 'files'
    archived = set()
    for source_root in roots:
        if not source_root.exists():
            continue
        if source_root.is_symlink() or not source_root.is_dir():
            raise ValueError('旧副本来源不是普通目录')
        for p in sorted(source_root.rglob('*')):
            if not p.is_file():
                continue
            relative = p.relative_to(source_root).as_posix()
            if relative in ('.stfolder', '.stignore') or relative.startswith('.stversions/'):
                continue
            safe_file(source_root, relative)
            sha, size = hash_file(p)
            target = targets.get(sha)
            if target is None:
                target = str(archive / sha[:2] / sha)
                if sha not in archived:
                    plan['history_bytes'] += size
                    archived.add(sha)
            plan['entries'].append(dict(source=str(p), source_root=str(source_root),
                                        relative=relative, target=target, sha256=sha, size=size))
            plan['bytes'] += size
            if len(plan['entries']) % 100 == 0:
                _emit(progress,len(plan['entries']),0,f'已检查 {len(plan["entries"])} 个旧副本文件')
    plan['estimated_freed_bytes'] = plan['bytes'] - plan['history_bytes']
    atomic_json(_plan_path(runtime, plan['plan_id']), plan)
    return plan


def execute_old_copies(runtime, plan_id, progress=None):
    from .deletion import safe_unlink_verified
    plan = read_json(_plan_path(runtime, plan_id))
    if (plan.get('kind') != 'project_old_copies' or runtime.account_id != plan['account_id']
            or str(runtime.output_root) != plan['root']):
        raise ValueError('旧副本清理清单与当前目录或账号不一致')
    if plan.get('state')=='preview':
        from .catalog import ResourceLibrary
        if _catalog_signature(ResourceLibrary(Path(plan['roots'][0])).list_works())!=plan['source_signature']:
            raise ValueError('旧库在清理预览后又有变化，未执行删除')
    # First archive every unique historical file. Nothing is removed in this pass.
    for item in plan['entries']:
        source = safe_file(item['source_root'], item['relative'])
        target = Path(item['target'])
        if not target.resolve().is_relative_to(runtime.output_root) or target.is_symlink():
            raise ValueError('目标校验路径越界')
        if source.exists() and hash_file(source) != (item['sha256'], item['size']):
            raise ValueError('旧副本已变化，请重新预览')
        if not target.exists():
            if not source.exists():
                raise ValueError('来源和目标都缺失，已停止清理')
            safe_file(runtime.output_root, target.relative_to(runtime.output_root).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source,target)
        if hash_file(target) != (item['sha256'], item['size']):
            raise ValueError('保留副本校验失败，未执行清理')
    snapshot = runtime.output_root / '.project-data' / 'history' / 'snapshots' / (plan_id + '.json')
    atomic_json(snapshot, plan)
    cleaned = 0; errors = []
    ordered=sorted(plan['entries'],key=lambda item:item['relative']=='library.json')
    for index,item in enumerate(ordered):
        try:
            if item['relative']=='library.json' and errors:
                raise ValueError('部分清理未完成，保留旧库标识供核对')
            target = Path(item['target'])
            if hash_file(target) != (item['sha256'],item['size']):
                raise ValueError('保留副本已变化，保留旧文件')
            source = Path(item['source'])
            if source.exists():
                safe_unlink_verified(source,Path(item['source_root']),item['sha256'],item['size'])
                cleaned += item['size']
        except (OSError,ValueError) as exc:
            errors.append(dict(path=item['source'],reason=str(exc)))
        if index % 100 == 0:
            _emit(progress,index+1,len(plan['entries']),f'已处理 {index+1}/{len(plan["entries"])} 个旧文件')
    plan.update(state='cleanup_partial' if errors else 'completed',cleaned_bytes=cleaned,errors=errors)
    atomic_json(_plan_path(runtime,plan_id),plan)
    if not errors:
        runtime.state['project_old_copies_retired']=True
        runtime.save()
    return plan


def preview_normalize(runtime):
    """Adopt named legacy folders in place, including flat Xingxing releases."""
    import re
    from ..config.series import load_meta
    if runtime.state.get('storage_mode') != 'projects':
        raise ValueError('请先切换为规范工程模式')
    plan = dict(plan_id=uuid.uuid4().hex, kind='project_normalize', root=str(runtime.output_root),
                account_id=runtime.account_id, entries=[], missing=[], state='preview')
    identities = {w['work_id'] for w in runtime.works()}
    for directory in sorted(runtime.output_root.iterdir()):
        if (not directory.is_dir() or directory.is_symlink() or (directory/'project.json').exists()
                or (directory/'library.json').exists()
                or not re.fullmatch(r'(周三涵做表情\d+|星星布丁第[零一二三四五六七八九十百千\d]+弹)',directory.name)):
            continue
        meta=load_meta(directory)
        if meta.account_id and meta.account_id != runtime.account_id:
            plan['missing'].append(dict(path=str(directory),reason='旧工程账号不一致'));continue
        meta.work_id=meta.work_id or uuid.uuid5(uuid.NAMESPACE_URL,
                        runtime.library.library_id+'/legacy-folder/'+directory.name).hex
        if meta.work_id in identities:
            plan['missing'].append(dict(path=str(directory),reason='同一作品已有规范工程，不能重复导入'));continue
        meta.account_id=runtime.account_id;meta.account_label=runtime.account_label
        meta.album_name=meta.album_name or directory.name
        intro=directory/'介绍.txt'
        if intro.is_file() and not meta.intro:
            meta.intro=intro.read_text(encoding='utf-8')
        files=[];meanings=read_meanings(directory);destinations=set()
        for p in sorted(directory.rglob('*')):
            if not p.is_file():continue
            logical=p.relative_to(directory).as_posix()
            target=('最终版/'+p.name if p.parent==directory and p.suffix.lower()
                    in ('.png','.gif','.webp','.jpg','.jpeg') else logical)
            safe_file(directory,logical);safe_file(directory,target)
            if target.casefold() in destinations:
                plan['missing'].append(dict(path=str(p),reason='最终版文件重名，保留原件并停止'))
            destinations.add(target.casefold())
            sha,size=hash_file(p)
            files.append(dict(logical=logical,target=target,sha256=sha,size=size))
        if not meanings:
            names=[Path(f['target']).stem for f in files
                   if f['target'].startswith('最终版/') and Path(f['target']).suffix.lower()=='.png']
            meanings={str(i+1):n for i,n in enumerate(names)}
        plan['entries'].append(dict(path=str(directory),metadata=meta.to_dict(),files=files,
                                    meaning_map=meanings,characters=read_characters(directory)))
    atomic_json(_plan_path(runtime,plan['plan_id']),plan)
    return plan


def execute_normalize(runtime,plan_id):
    plan=read_json(_plan_path(runtime,plan_id))
    if (plan.get('kind')!='project_normalize' or plan['missing']
            or plan['account_id']!=runtime.account_id or plan['root']!=str(runtime.output_root)):
        raise ValueError('旧目录规范预览无效或仍有冲突')
    for entry in plan['entries']:
        path=Path(entry['path'])
        if path.parent!=runtime.output_root or (path/'project.json').exists():
            raise ValueError('目标工程已变化，请重新预览')
        for item in entry['files']:
            source=safe_file(path,item['logical'])
            if not source.exists():source=safe_file(path,item['target'])
            if hash_file(source)!=(item['sha256'],item['size']):
                raise ValueError('旧目录文件已变化，请重新预览')
    for entry in plan['entries']:
        path=Path(entry['path'])
        for item in entry['files']:
            if item['target']==item['logical']:continue
            source=safe_file(path,item['logical']);target=safe_file(path,item['target'])
            if not source.exists():continue  # resume a verified prior move
            if target.exists():raise ValueError('目标文件已存在，拒绝覆盖')
            target.parent.mkdir(parents=True,exist_ok=True)
            source.rename(target)
        create_project(path,entry['metadata'],meanings=entry['meaning_map'],characters=entry['characters'])
        runtime.capture(path)
    plan['state']='completed'
    atomic_json(_plan_path(runtime,plan_id),plan)
    return dict(plan_id=plan_id,state='completed',normalized=len(plan['entries']))
