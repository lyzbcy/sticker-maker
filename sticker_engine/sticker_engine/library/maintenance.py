"""Clean only snapshotted application caches that have verified shared copies."""
from pathlib import Path

from .resources import hash_file
from .deletion import safe_unlink_verified
from .runtime import read_json, write_json, is_private


def record_cache_plan(runtime, plan):
    if plan.get('mode') != 'migration' or not plan.get('cleanup'):
        return
    library = runtime.library
    local_library = runtime.local / 'library'
    library_roots = {local_library, library.root}
    settings_root = runtime.output_root.parent / 'settings'
    revisions = {}
    for work in library.list_works():
        _work, graph, _complete = library._analyze_work(work['account_id'], work['work_id'])
        for revision in graph.values():
            revisions[(work['account_id'], work['work_id'], revision['revision_id'])] = revision
    items = {}

    def add(source, root, reference, target_relative, provenance):
        source, root = Path(source), Path(root)
        if not source.is_file() or source.is_symlink() or root.is_symlink():
            return
        try:
            relative = source.relative_to(root)
        except ValueError:
            return
        if is_private(relative) or root.resolve() not in source.resolve().parents:
            return
        if any(root.joinpath(*relative.parts[:i]).is_symlink()
               for i in range(len(relative.parts) + 1)):
            return
        digest, size = hash_file(source)
        if reference and (digest, size) != (reference['sha256'], reference['size']):
            return  # This file is not the captured resource; leave it alone.
        items[str(source)] = {'path': str(source), 'root': str(root), 'sha256': digest,
            'size': size, 'target_relative': target_relative, 'revision_id': provenance}

    # Derive deletion candidates from validated revisions, never from a broad
    # scan of arbitrary files that happen to have matching content hashes.
    for (account, work_id, revision_id), revision in revisions.items():
        manifest = f'accounts/{account}/works/{work_id}/revisions/{revision_id}.json'
        for source_library in library_roots:
            add(source_library / manifest, source_library, None, manifest, revision_id)
        for logical, reference in revision['files'].items():
            digest = reference['sha256']
            object_path = f'objects/{digest[:2]}/{digest}'
            for source_library in library_roots:
                add(source_library / object_path, source_library, reference, object_path, revision_id)
            if account != runtime.account_id or revision['metadata'].get('kind') != 'settings':
                continue
            # Aggregate prefs/series are local projections, not original assets.
            if logical not in ('prefs.yaml', 'series.json') and not logical.startswith('series/'):
                add(settings_root / logical, settings_root, reference, object_path, revision_id)
            if logical.startswith(('custom_bases/', 'reference_library/')):
                add(runtime.user_data / logical, runtime.user_data, reference, object_path, revision_id)

    for source_path, marker in runtime.state.get('paths', {}).items():
        source_root = Path(source_path)
        if marker.get('account_id') != runtime.account_id:
            continue
        if source_root.parent not in (runtime.output_root, runtime.user_data / 'episodes'):
            continue
        revision = revisions.get((runtime.account_id, marker.get('work_id'), marker.get('revision_id')))
        if not revision:
            continue
        for logical, reference in revision['files'].items():
            digest = reference['sha256']
            add(source_root / logical, source_root, reference,
                f'objects/{digest[:2]}/{digest}', revision['revision_id'])

    grouped = {}
    for item in items.values():
        group = grouped.setdefault(item['root'], {'path': item['root'], 'files': 0, 'bytes': 0})
        group['files'] += 1
        group['bytes'] += item['size']
    plan['cache_cleanup'] = {'files': len(items), 'bytes': sum(i['size'] for i in items.values()),
                             'sources': list(grouped.values())}
    plan['workspace_path'] = str(runtime.output_root)
    write_json(runtime.local / 'cache_plans' / (plan['plan_id'] + '.json'), {
        'target': plan['target'], 'items': list(items.values()), 'errors': [], 'complete': False})



def cleanup_cache_plan(runtime, plan_id):
    path = runtime.local / 'cache_plans' / (plan_id + '.json')
    if not path.exists():
        return {'cleaned': 0, 'errors': []}
    plan = read_json(path)
    destination = runtime.library.root.resolve()
    if destination != Path(plan['target']).resolve():
        raise ValueError('当前资源库不是本次迁移的目标，不能清理旧缓存')
    errors, count = [], 0
    for item in plan['items']:
        source = Path(item['path'])
        root = Path(item['root'])
        if not source.exists():
            continue
        try:
            relative = source.relative_to(root)
            chain = [root.joinpath(*relative.parts[:i]) for i in range(len(relative.parts) + 1)]
            if any(p.is_symlink() for p in chain) or root.resolve() not in source.resolve().parents:
                raise ValueError('源缓存路径已变化')
            if destination == root.resolve() or destination in source.resolve().parents:
                raise ValueError('不能删除当前资源库文件')
            expected = (item['sha256'], item['size'])
            if hash_file(source) != expected:
                raise ValueError('源缓存已变化，保留此文件')
            target = destination / item['target_relative']
            if destination not in target.resolve().parents or hash_file(target) != expected:
                raise ValueError('目标副本未通过校验，保留源缓存')
            safe_unlink_verified(source, root, item['sha256'], item['size'])
            count += 1
        except (OSError, ValueError) as exc:
            errors.append(f'{source.name}: {exc}')
    plan.update(errors=errors, complete=not errors)
    write_json(path, plan)
    return {'cleaned': count, 'errors': errors}
