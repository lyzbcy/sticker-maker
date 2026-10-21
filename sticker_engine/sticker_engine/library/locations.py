"""Discover explicitly selected folders and remember an existing resource location."""
import copy
import uuid
from pathlib import Path

from .catalog import ResourceLibrary
from .runtime import read_json, _ACTIVE_RUNTIME_CACHE, _ACTIVE_RUNTIME_LOCK
from .resources import validate_identifier
from ..project import atomic_json, project_directories, read_project


def inspect_location(value):
    if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
        raise ValueError('请选择资源所在的绝对路径')
    root = Path(value).resolve()
    if not root.is_dir():
        raise ValueError('资源目录不存在或尚未同步到本机')
    # Only the chosen folder, its parent for a single project, and immediate
    # children. Never search the entire disk or follow directory links.
    if (root / 'project.json').is_file():
        root = root.parent
    folders = [root]
    if not any((root / marker).is_file() for marker in ('projects.json', 'library.json')):
        folders += sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                          and not (getattr(p, 'is_junction', lambda: False)())
                          and not p.name.startswith('.'))
    found, errors = [], []
    for folder in folders:
        project_marker, legacy_marker = folder / 'projects.json', folder / 'library.json'
        if not project_marker.is_file() and not legacy_marker.is_file():
            continue
        try:
            accounts = {}
            if project_marker.is_file():
                data = read_json(project_marker)
                if data.get('format') != 'sticker-maker-project-collection' or not data.get('library_id'):
                    raise ValueError('工程集合清单无效')
                mode, library_id = 'projects', data['library_id']
                for p in project_directories(folder):
                    meta = read_project(p)['metadata']
                    if meta.get('account_id'):
                        accounts[meta['account_id']] = meta.get('account_label') or meta['account_id']
            else:
                library = ResourceLibrary(folder)
                mode, library_id = 'legacy', library.library_id
                for work in library.list_works():
                    meta = (work.get('revision') or {}).get('metadata') or {}
                    key = work['account_id']
                    accounts[key] = meta.get('account_label') or accounts.get(key) or key
            validate_identifier(library_id)
            for key in accounts:
                validate_identifier(key)
            found.append(dict(path=str(folder), name=folder.name, storage_mode=mode,
                              library_id=library_id, accounts=[dict(account_id=k, account_label=v)
                                                             for k, v in sorted(accounts.items())]))
        except (OSError, ValueError, KeyError) as exc:
            errors.append(dict(path=str(folder), message=str(exc)))
    return dict(candidates=found, errors=errors)


def connect_location(rt, args):
    if args.get('confirm_account') is not True:
        raise ValueError('请确认所选资源属于这个账号')
    candidates = inspect_location(args.get('path'))['candidates']
    selected = next((c for c in candidates if c['path'] == str(Path(args['path']).resolve())
                     and c['library_id'] == args.get('library_id')), None)
    if not selected:
        raise ValueError('资源位置或身份已变化，请重新选择文件夹')
    account = next((a for a in selected['accounts'] if a['account_id'] == args.get('account_id')), None)
    if not account:
        raise ValueError('请选择此资源库内的账号')
    previous = copy.deepcopy(rt.state)
    # Archive local connection state; do not merge or reattribute any artwork.
    backup = rt.local / 'connections' / (uuid.uuid4().hex + '.json')
    atomic_json(backup, previous)
    state = dict(device_id=previous['device_id'], paths={}, hidden=[],
                 accounts={account['account_id']: account['account_label']},
                 account_id=account['account_id'], account_label=account['account_label'],
                 library_id=selected['library_id'], settings_versions={},
                 identity_aliases={}, identity_conflicts=[], last_rows=[])
    if selected['storage_mode'] == 'projects':
        state.update(storage_mode='projects', project_root=selected['path'])
        if (previous.get('project_root') == selected['path']
                and previous.get('library_id') == selected['library_id']):
            for key in ('project_migration_id', 'project_old_copies_retired'):
                if key in previous:
                    state[key] = previous[key]
    else:
        state.update(root=selected['path'], workspace_base=str(
            Path(selected['path']).parent / '.sticker-maker-workspaces' / previous['device_id']))
    from .runtime import runtime_for_user_data
    def invalidate():
        with _ACTIVE_RUNTIME_LOCK:
            import os
            _ACTIVE_RUNTIME_CACHE.pop(os.path.normcase(str(rt.user_data.resolve())), None)
    try:
        atomic_json(rt.config_file, state)
        invalidate()
        current = runtime_for_user_data(rt.user_data)
        result = current.refresh(capture=False)
        if result.get('offline'):
            raise ValueError('资源目录不可用，已保留原连接')
        return result
    except Exception:
        atomic_json(rt.config_file, previous)
        invalidate()
        raise
