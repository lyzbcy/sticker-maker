"""Direct project runtime, retaining account/submit gates without a second store."""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

from ..project import (atomic_json, create_project, file_manifest, folder_name,
                       named_destination, project_directories, read_project,
                       rename_project, safe_file, seal_project, update_project)
from ..config.series import EpisodeMeta, load_meta, save_meta
from ..publish.platform_data import SHELFABLE_STATUSES
from .runtime import LibraryRuntime, account_key, read_json


class ProjectCatalog:
    """Small compatibility surface for identity and durable submission records.

    Episode bytes only exist under named project directories. Records contain no
    artwork; unlike ResourceLibrary there is no objects/ or materialize operation.
    """
    def __init__(self, runtime):
        self.runtime = runtime
        self.root = runtime.output_root
        collection = read_json(self.root / 'projects.json')
        if collection.get('format') != 'sticker-maker-project-collection':
            raise ValueError('不是规范工程集合')
        self.library_id = collection['library_id']
        if self.library_id != runtime.state.get('library_id'):
            raise ValueError('工程集合身份已变化，请重新连接')

    def list_works(self, account_id=None):
        result = []
        for p in project_directories(self.root):
            data = read_project(p)
            meta = data['metadata']
            if account_id and meta.get('account_id') != account_id:
                continue
            missing = [logical for logical, ref in data['files'].items()
                       if not safe_file(p, logical).is_file()
                       or safe_file(p, logical).stat().st_size != ref['size']]
            conflicts = [str(f) for f in p.rglob('*.sync-conflict-*')]
            state = ('conflict' if conflicts else 'deleted' if data.get('deleted') else
                     'pending' if missing else 'placeholder' if meta.get('resource_placeholder')
                     else 'available')
            rev = dict(metadata=dict(meta, kind='episode'), files=data['files'],
                       revision_id=data['revision_id'], work_id=meta['work_id'],
                       account_id=meta['account_id'], parents=[], deleted=data.get('deleted', False))
            result.append(dict(account_id=meta['account_id'], work_id=meta['work_id'],
                               state=state, revision=rev, heads=[rev], path=str(p),
                               missing=missing, sync_conflicts=conflicts))
        records = self.root / '.project-data' / 'records'
        if records.exists():
            for p in records.glob('*/*.json'):
                rev = read_json(p)
                if account_id and rev['account_id'] != account_id:
                    continue
                conflicts = list(p.parent.glob(p.stem + '.sync-conflict-*'))
                result.append(dict(account_id=rev['account_id'], work_id=rev['work_id'],
                                   state='conflict' if conflicts else 'available',
                                   heads=[rev], revision=rev, sync_conflicts=[str(c) for c in conflicts]))
        # Two folders carrying one identity must never be silently selected.
        by_id = {}
        for w in result:
            key = (w['account_id'], w['work_id'])
            if key in by_id:
                by_id[key]['state'] = w['state'] = 'conflict'
            by_id[key] = w
        return result

    def read_work(self, account_id, work_id):
        from .resources import validate_identifier
        validate_identifier(account_id); validate_identifier(work_id)
        # Identity lookup must not re-stat every image in every other project.
        # Folder additions/renames invalidate this index via root mtime.
        stamp = self.root.stat().st_mtime_ns
        if getattr(self, '_index_stamp', None) != stamp:
            self._index = {}
            for p in project_directories(self.root):
                m = read_project(p)['metadata']
                self._index.setdefault((m['account_id'], m['work_id']), []).append(p)
            self._index_stamp = stamp
        paths = self._index.get((account_id, work_id), [])
        if not paths:
            record = self.root / '.project-data' / 'records' / account_id / (work_id + '.json')
            if record.is_file():
                rev = read_json(record)
                conflict = bool(list(record.parent.glob(record.stem + '.sync-conflict-*')))
                return dict(account_id=account_id, work_id=work_id, state='conflict' if conflict else 'available',
                            heads=[rev], revision=rev, sync_conflicts=[])
            return dict(account_id=account_id, work_id=work_id, state='placeholder', heads=[], revision=None)
        # Restrict enumeration to this project while sharing the same validator.
        if len(paths) > 1:
            raise ValueError('同一作品有多个工程目录，请先处理冲突')
        p = paths[0]
        data = read_project(p)
        meta = data['metadata']
        missing = [k for k,r in data['files'].items()
                   if not safe_file(p,k).is_file() or safe_file(p,k).stat().st_size != r['size']]
        conflicts = [str(f) for f in p.rglob('*.sync-conflict-*')]
        state = ('conflict' if conflicts else 'deleted' if data.get('deleted') else 'pending' if missing
                 else 'placeholder' if meta.get('resource_placeholder') else 'available')
        rev = dict(account_id=account_id, work_id=work_id, revision_id=data['revision_id'], metadata=dict(meta, kind='episode'),
                   files=data['files'], parents=[], deleted=bool(data.get('deleted')))
        matches = [dict(account_id=account_id, work_id=work_id, state=state, revision=rev, heads=[rev],
                        path=str(p), missing=missing, sync_conflicts=conflicts)]
        if matches:
            if len(matches) > 1:
                raise ValueError('同一作品有多个工程目录，请先处理冲突')
            return matches[0]
        return dict(account_id=account_id, work_id=work_id, state='placeholder', heads=[], revision=None)

    def write_revision(self, account_id, work_id, metadata, files, parents=None, deleted=False):
        from .resources import validate_identifier
        validate_identifier(account_id); validate_identifier(work_id)
        work = self.read_work(account_id, work_id)
        rev = work.get('revision')
        if work.get('state') == 'conflict':
            raise ValueError('工程或操作记录存在同步冲突')
        if rev and parents is not None and parents != [rev['revision_id']]:
            raise ValueError('工程版本已变化，请重新读取')
        if metadata.get('kind', 'episode') == 'episode':
            if not work.get('path'):
                raise ValueError('请先创建规范工程')
            p = Path(work['path'])
            def change(d):
                d.update(metadata=metadata, files=files, deleted=deleted)
            updated = update_project(p, change, rev['revision_id'])
            return dict(rev, metadata=metadata, files=files, deleted=deleted,
                        revision_id=updated['revision_id'])
        new = dict(account_id=account_id, work_id=work_id, revision_id=uuid.uuid4().hex,
                   metadata=metadata, files=files, parents=parents or [], deleted=deleted)
        atomic_json(self.root / '.project-data' / 'records' / account_id / (work_id + '.json'), new)
        return new


class ProjectRuntime(LibraryRuntime):
    def works(self):
        return [w for w in self.library.list_works(self.account_id)
                if (w.get('revision') or {}).get('metadata', {}).get('kind', 'episode') == 'episode']

    @property
    def output_root(self):
        root = Path(self.state['project_root']).expanduser()
        if not root.is_absolute():
            raise ValueError('工程根目录必须是绝对路径')
        return root.resolve()

    @property
    def library(self):
        if not self.output_root.is_dir():
            raise FileNotFoundError('工程目录离线')
        # Check collection identity on each access; reuse only the in-memory
        # path index, never cached artwork or a second set of file bytes.
        collection = read_json(self.output_root / 'projects.json')
        if (collection.get('library_id') != self.state.get('library_id')
                or collection.get('format') != 'sticker-maker-project-collection'
                or collection.get('schema_version') != 1):
            raise ValueError('工程集合身份已变化或未同步完整')
        if (getattr(self, '_project_catalog', None) is None
                or self._project_catalog.root != self.output_root):
            self._project_catalog = ProjectCatalog(self)
        return self._project_catalog

    @property
    def settings_root(self):
        return self.output_root / '.project-data' / 'settings' / self.account_id

    def bind(self, account, confirm_legacy=False):
        self.state.update(account_id=account_key(account), account_label=str(account).strip())
        self.state['accounts'][self.account_id] = self.account_label
        self._rows_at = 0
        self.save()
        return self.status()

    def connect(self, path):
        raise ValueError('规范工程模式请使用“连接工程目录”；旧资源库请先迁移')

    def path_for(self, work_id):
        work = self.library.read_work(self.account_id, work_id)
        if not work.get('path'):
            raise ValueError('工程目录不存在')
        return Path(work['path'])

    def _work_path_map(self):
        return {w['work_id']: w['path'] for w in self.works()}

    def _materialize(self, work, path=None, force=False):
        # The project already IS the editable directory. Never reconstruct it.
        return

    def placeholder(self, row):
        sid = str(row.get('StikerID') or '')
        if not sid:
            raise ValueError('平台作品缺少 ID')
        for w in self.works():
            if w['revision']['metadata'].get('platform_item_id') == sid:
                return Path(w['path'])
        meta = EpisodeMeta(album_name=str(row.get('Name') or ''), platform_item_id=sid,
                           account_id=self.account_id, account_label=self.account_label,
                           resource_placeholder=True)
        meta.work_id = self._identity(meta)
        target = named_destination(self.output_root, meta.album_name, meta.work_id)
        target.mkdir(exist_ok=False)
        create_project(target, meta.to_dict())
        return target

    def capture(self, path):
        self.require_account()
        path = Path(path).resolve()
        if path.parent != self.output_root or path.is_symlink():
            raise ValueError('作品必须位于当前工程目录内')
        meta = load_meta(path)
        if meta.account_id and meta.account_id != self.account_id:
            raise ValueError('作品所属账号不一致')
        meta.account_id, meta.account_label = self.account_id, self.account_label
        meta.work_id = meta.work_id or uuid.uuid4().hex
        if read_project(path) is None:
            from ..project import read_meanings, read_characters
            create_project(path, meta.to_dict(), meanings=read_meanings(path),
                           characters=read_characters(path))
        else:
            save_meta(path, meta)
        if read_project(path)['mode'] == 'full':
            self._import_custom_assets(path)
        # Sidecars are producer outputs; absorb them, rather than keep two
        # competing metadata authorities in the portable format.
        project = read_project(path)
        meanings = path / 'meaning_map.json'
        if meanings.exists():
            value = read_json(meanings)
            project = update_project(path, lambda d: d.update(meaning_map=value))
            meanings.unlink()
        card = path / '本次制作角色.md'
        if card.exists():
            chars = []
            for line in card.read_text(encoding='utf-8').splitlines():
                if line.startswith('角色：'):
                    chars = [c for c in line[3:].split('、') if c]
            update_project(path, lambda d: d.update(characters=chars))
            card.unlink()
        intro = path / '介绍.txt'
        if intro.is_file():
            value = intro.read_text(encoding='utf-8')
            update_project(path, lambda d: d['metadata'].update(intro=value))
            intro.unlink()
        legacy_meta = path / 'meta.json'
        if legacy_meta.is_file():
            legacy_meta.unlink()
        actual = read_project(path)
        if actual['mode'] == 'delivery':
            # A compact project remains compact even if an external tool drops
            # an old raw folder beside it. Do not silently re-adopt that folder.
            if any((path / name).is_dir() and any(f.is_file() for f in (path / name).rglob('*'))
                   for name in ('原图', '参考图')):
                raise ValueError('精简工程出现额外源图，请明确导入完整工程后再使用')
        # Paths remain stable during the capture hook; generation and rename
        # commands finalize the readable name before returning it to the UI.
        result = seal_project(path)
        if (path/'最终版').is_dir() and list((path/'最终版').glob('*.png')):
            result = update_project(path, lambda d: d['metadata'].update(resource_placeholder=False))
        self._rows_at = 0
        return dict(work_id=meta.work_id, revision_id=result['revision_id'])

    def _import_custom_assets(self, path):
        import shutil
        meta = load_meta(path)
        changed = False
        for field in ('cover_custom', 'banner_custom', 'icon_custom'):
            raw = getattr(meta, field)
            if not raw:
                continue
            source = Path(raw)
            source = source if source.is_absolute() else path / source
            if not source.is_file() or source.is_symlink():
                raise ValueError('自定义素材缺失或是链接：' + field)
            if not source.resolve().is_relative_to(path):
                relative = '自定义素材/' + field + source.suffix.lower()
                dest = safe_file(path, relative)
                if dest.exists() and dest.read_bytes() != source.read_bytes():
                    relative = '自定义素材/' + field + '-' + uuid.uuid4().hex[:8] + source.suffix.lower()
                    dest = safe_file(path, relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            else:
                relative = source.resolve().relative_to(path).as_posix()
            if relative != raw:
                setattr(meta, field, relative); changed = True
        if changed:
            save_meta(path, meta)

    def capture_all(self):
        # Metadata lives in project.json immediately; no full-library copying.
        return {'captured': 0}

    def refresh(self, capture=True, max_age=None):
        self._rows_at = 0
        return self.status()

    def commit_platform_metadata(self, path, meta):
        current = load_meta(path)
        if current.work_id != meta.work_id or current.account_id != self.account_id:
            raise ValueError('平台状态账号或作品身份不一致')
        save_meta(path, meta)
        self._rows_at = 0

    def finish_platform_sync(self):
        self._rows_at = 0
        self.save()

    def rows(self):
        try:
            works = self.works()
            # works() legacy helper swallows offline errors, so validate first.
            self.library
        except (OSError, ValueError):
            return [dict(r, offline=True, can_edit=False, can_publish=False, can_shelf=False)
                    for r in self.state.get('last_rows', [])]
        rows = []
        platform_ids = {}
        for w in works:
            sid = w['revision']['metadata'].get('platform_item_id')
            if sid and w['state'] != 'deleted':
                platform_ids.setdefault(sid, []).append(w['work_id'])
        for w in works:
            if w['state'] == 'deleted' or w['work_id'] in self.state['hidden']:
                continue
            p = Path(w['path']); meta = w['revision']['metadata']; data = read_project(p)
            finals = list((p / '最终版').glob('*.png'))
            ready = w['state'] == 'available'
            sid = meta.get('platform_item_id')
            if sid and len(platform_ids.get(sid, [])) > 1:
                ready = False
                w['state'] = 'conflict'
            required = ['横幅/横幅.png', '封面/封面.png', '图标/图标.png']
            cover = p / required[1]
            if not cover.exists():
                cover = finals[0] if finals else None
            rows.append(dict(meta, name=p.name, path=str(p), resource_state=w['state'],
                             can_edit=ready, can_publish=bool(ready and len(finals) >= 8
                             and data.get('meaning_map') and meta.get('intro')
                             and all((p / logical).is_file() for logical in required)),
                             can_shelf=w['state'] in ('available', 'placeholder')
                             and meta.get('platform_status') in SHELFABLE_STATUSES,
                             sticker_count=len(finals), cover=str(cover) if cover else '',
                             complete=bool(finals), missing=w['missing'],
                             project_mode=data['mode'], can_edit_sources=data['mode'] == 'full'))
        self.state['last_rows'] = copy.deepcopy(rows)
        return rows

    def status(self):
        from .operations import unresolved
        counts = dict.fromkeys(('available', 'placeholder', 'pending', 'conflict', 'deleted'), 0)
        warnings = []; works = []; offline = False
        try:
            self.library
            works = self.works()
        except (OSError, ValueError) as exc:
            offline = True
            warnings.append({'message': str(exc)})
        for w in works:
            counts[w['state']] += 1
        return dict(storage_mode='projects', connected=True, offline=offline,
                    project_migration_id=self.state.get('project_migration_id'),
                    project_old_copies_retired=bool(self.state.get('project_old_copies_retired')),
                    root=str(self.output_root), workspace_path='', library_id=self.state['library_id'],
                    account_id=self.account_id, account_label=self.account_label,
                    accounts=[dict(account_id=k, account_label=v) for k,v in self.state['accounts'].items()],
                    counts=counts, warnings=warnings, conflicts=[w for w in works if w['state']=='conflict'],
                    settings_conflicts=[], settings_missing=[], tasks=[],
                    hidden_works=[dict(work_id=w['work_id'], album_name=w['revision']['metadata'].get('album_name'))
                                  for w in works if w['work_id'] in self.state['hidden']],
                    deleted_works=[dict(work_id=w['work_id'], album_name=w['revision']['metadata'].get('album_name'))
                                   for w in works if w['state']=='deleted'],
                    unresolved_operations=[] if offline else unresolved(self))

    def resolve(self, *args, **kwargs):
        raise ValueError('规范工程存在冲突时请先保留双方文件并处理同步冲突，不自动覆盖')

    def materialize_chosen(self, *args, **kwargs):
        raise ValueError('规范工程直接读取原目录，无需还原工作副本')
