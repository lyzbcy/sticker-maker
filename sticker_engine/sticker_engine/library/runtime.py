"""Local account bindings and episode adapters for the immutable shared library.

Device state never enters Syncthing. Each materialized episode remembers the
revision it was edited from, so an offline edit cannot silently overwrite a peer.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import copy
from pathlib import Path

from ..config.series import EpisodeMeta, load_meta, save_meta
from .catalog import ResourceLibrary
from .resources import hash_file
from .settings import SharedSettings


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'数据文件无法读取，已保留原文件：{path.name}') from exc


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def account_key(account):
    value = str(account or '').strip().casefold()
    if not value or len(value) > 254:
        raise ValueError('请输入有效的平台登录账号')
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def fingerprint(metadata, files):
    return hashlib.sha256(json.dumps([metadata, files], sort_keys=True,
                                    ensure_ascii=False).encode()).hexdigest()


def is_private(path):
    names = {p.casefold() for p in Path(path).parts}
    return bool(names & {'.env', 'auth.json', 'publish_storage.json',
                         'publish_credentials.json', '.stfolder', '.stignore',
                         '.stversions', 'cookies', '.browser-data', 'node_modules'}) or any(
        n.startswith(('.syncthing.', '~syncthing~', '.resource-')) or
        '.sync-conflict-' in n for n in names)


class LibraryRuntime:
    def __init__(self, user_data):
        self.user_data = Path(user_data).resolve()
        self.local = self.user_data / 'resource_library'
        self.config_file = self.local / 'device.json'
        self.state = read_json(self.config_file)
        self.state.setdefault('device_id', uuid.uuid4().hex)
        self.state.setdefault('paths', {})
        self.state.setdefault('hidden', [])
        self.state.setdefault('accounts', {})
        self.state.setdefault('settings_versions', {})
        self.state.setdefault('identity_aliases', {})
        self.state.setdefault('identity_conflicts', [])
        self._library_cache = None
        self._library_cache_root = None
        self._library_cache_signature = None

    def save(self):
        write_json(self.config_file, self.state)

    @property
    def enabled(self):
        return bool(self.account_id)

    @property
    def account_id(self):
        return self.state.get('account_id', '')

    @property
    def account_label(self):
        return self.state.get('account_label', '')

    @property
    def library(self):
        root = self.state.get('root')
        if root:
            root = Path(root).expanduser().resolve()
            # A connected library is never recreated implicitly.  Keeping the
            # distinction matters when a Syncthing mount is temporarily gone:
            # callers must see an offline state instead of a new empty catalog.
            if not root.is_dir():
                raise FileNotFoundError(root)
            library_file = root / 'library.json'
            try:
                stat = library_file.stat()
                signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            except OSError:
                raise FileNotFoundError(library_file)
            if (self._library_cache is not None and self._library_cache_root == root
                    and self._library_cache_signature == signature):
                return self._library_cache
            lib = ResourceLibrary(root)
            if lib.library_id != self.state.get('library_id'):
                raise ValueError('目录中的资源库身份已变化，请重新连接')
            self._library_cache = lib
            self._library_cache_root = root
            self._library_cache_signature = signature
            return lib
        root = (self.local / 'library').resolve()
        library_file = root / 'library.json'
        try:
            stat = library_file.stat()
            signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except OSError:
            signature = None
        if (self._library_cache is not None and self._library_cache_root == root
                and self._library_cache_signature == signature):
            return self._library_cache
        lib = ResourceLibrary(root, create=True)
        self._library_cache = lib
        self._library_cache_root = root
        try:
            stat = (root / 'library.json').stat()
            self._library_cache_signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except OSError:
            self._library_cache_signature = None
        return lib

    @property
    def workspace_base(self):
        """Per-device materialization root for the active library/account."""

        return Path(self.state.get('workspace_base') or self.local / 'workspaces').expanduser().resolve()

    @property
    def output_root(self):
        if not self.enabled:
            return self.user_data / 'episodes'
        lid = self.state.get('library_id') or self.library.library_id
        base = self.workspace_base
        return base / lid / self.account_id / 'episodes'

    def require_account(self):
        if not self.account_id:
            raise ValueError('请先在账号与资源库中绑定平台登录账号')

    def bind(self, account, confirm_legacy=False):
        was_bound = bool(self.account_id)
        previous = copy.deepcopy(self.state)
        key = account_key(account)
        unbound = [p for p in (self.user_data / 'episodes').glob('episode*')
                   if p.is_dir() and not load_meta(p).account_id]
        if unbound and not confirm_legacy:
            raise ValueError(f'发现 {len(unbound)} 个旧作品，请确认其账号归属后绑定')
        try:
            self.state.update(account_id=key, account_label=str(account).strip())
            self.state['library_id'] = self.library.library_id
            self.state['accounts'][key] = str(account).strip()
            self.save()

            # Legacy settings are copied only for the first explicit bind.
            # On an account switch the old account's settings must not leak
            # into the new account workspace.
            seed_result = None
            if not was_bound:
                seed_result = SharedSettings(self).seed_legacy()

            for path in unbound:
                meta = load_meta(path)
                meta.account_id, meta.account_label = key, self.account_label
                meta.work_id = self._identity(meta, path)
                save_meta(path, meta)
                self.capture(path)

            # Capture the seeded settings before the first refresh so the
            # initial account bind is represented by immutable shared heads.
            if not was_bound:
                result = SharedSettings(self).capture()
                if seed_result and seed_result.get('missing'):
                    result['missing'] = list(seed_result['missing']) + list(result.get('missing') or [])
                self.state['settings_seed_missing'] = list(seed_result.get('missing') or [])
                self._record_settings_result(result)
            self.refresh(capture=False)
        except Exception:
            self.state = previous
            self._library_cache = None
            self._library_cache_root = None
            self._library_cache_signature = None
            self.save()
            raise
        return self.status()

    def _identity(self, meta, path=None, stable=False):
        if meta.work_id:
            return meta.work_id
        if meta.platform_item_id:
            # The deterministic external identity also hydrates a placeholder.
            return uuid.uuid5(uuid.NAMESPACE_URL,
                              self.account_id + '/wechat/' + meta.platform_item_id).hex
        # New locally generated drafts intentionally get independent UUIDs.
        # Legacy directory import opts into a stable content identity so a
        # repeated import does not create a duplicate work.
        if not stable:
            return uuid.uuid4().hex
        payload = meta.to_dict()
        for key in ('work_id', 'account_id', 'account_label', 'resource_placeholder'):
            payload.pop(key, None)
        files = []
        if path is not None:
            root = Path(path)
            if root.is_dir() and not root.is_symlink():
                for item in sorted(root.rglob('*')):
                    if not item.is_file() or item.is_symlink() or item.name == 'meta.json' or is_private(item):
                        continue
                    digest, size = hash_file(item)
                    files.append((item.relative_to(root).as_posix(), digest, size))
        canonical = json.dumps([payload, files], ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(canonical).hexdigest()[:32]

    def _reconcile_platform_identities(self):
        """Collapse a resource-backed work and its pure platform placeholder.

        A generated draft can acquire a platform ID after a publish, while a
        second device may already have created a deterministic placeholder for
        that ID.  Preserve the placeholder's revision history as an alias
        tombstone; two resource-backed works remain separate and are surfaced
        as an identity conflict.
        """
        if not self.enabled:
            return
        groups = {}
        for work in self.library.list_works(self.account_id):
            rev = work.get('revision') or (work.get('heads') or [{}])[0]
            meta = rev.get('metadata', {})
            sid = str(meta.get('platform_item_id') or '').strip()
            if sid:
                groups.setdefault(sid, []).append(work)
        # Recompute this set from the current catalog on every refresh.  A
        # device-local stale ID would otherwise keep a deleted duplicate
        # blocked forever after the user removes one binding.
        conflicts = set()
        aliases = dict(self.state.get('identity_aliases') or {})
        for sid, works in groups.items():
            resources = []
            placeholders = []
            for work in works:
                rev = work.get('revision')
                if not rev or work.get('state') in ('deleted', 'pending', 'conflict'):
                    continue
                if work.get('state') == 'available' and rev.get('files'):
                    resources.append(work)
                elif work.get('state') == 'placeholder' and not rev.get('files'):
                    placeholders.append(work)
            if len(resources) > 1:
                conflicts.update(w['work_id'] for w in resources)
                continue
            if len(resources) != 1:
                continue
            resource = resources[0]
            conflicts.discard(resource['work_id'])
            for placeholder in placeholders:
                if placeholder['work_id'] == resource['work_id']:
                    continue
                heads = placeholder.get('heads') or []
                if not heads:
                    continue
                current = placeholder.get('revision') or heads[0]
                if current.get('metadata', {}).get('alias_of') == resource['work_id']:
                    aliases[placeholder['work_id']] = resource['work_id']
                    continue
                metadata = dict(current.get('metadata') or {})
                metadata.update(alias_of=resource['work_id'], identity_alias=True,
                               platform_item_id=sid)
                self.library.write_revision(self.account_id, placeholder['work_id'],
                                            metadata, current.get('files') or {},
                                            parents=[head['revision_id'] for head in heads],
                                            deleted=True)
                aliases[placeholder['work_id']] = resource['work_id']
        self.state['identity_aliases'] = aliases
        self.state['identity_conflicts'] = sorted(conflicts)
        self.save()

    def works(self):
        if not self.enabled:
            return []
        try:
            works = self.library.list_works(self.account_id)
        except (OSError, ValueError):
            return []
        return [w for w in works
                if (w.get('revision') or (w.get('heads') or [{}])[0]).get(
                    'metadata', {}).get('kind', 'episode') == 'episode']

    def placeholder(self, row):
        self.require_account()
        sid = str(row.get('StikerID') or '')
        if not sid:
            raise ValueError('平台作品缺少 ID，不能自动建立占位符')
        for p in self.output_root.glob('episode*'):
            m = load_meta(p)
            if m.account_id == self.account_id and m.platform_item_id == sid:
                return p
        meta = EpisodeMeta(album_name=str(row.get('Name') or ''),
                           platform_item_id=sid, account_id=self.account_id,
                           account_label=self.account_label, resource_placeholder=True)
        meta.work_id = self._identity(meta)
        # Rehydrate an existing catalog work when the local workspace was
        # removed.  Creating an empty child revision here would branch an
        # available work and hide its resources behind a conflict.
        work = self.library.read_work(self.account_id, meta.work_id)
        if work.get('revision') and work.get('state') in ('available', 'placeholder'):
            self._materialize(work)
            return self.path_for(meta.work_id)
        if work.get('state') in ('pending', 'conflict'):
            raise ValueError('该作品版本尚未同步完整或存在冲突，请先处理资源库状态')
        path = self.output_root / ('episode_' + meta.work_id)
        save_meta(path, meta)
        return path

    def _source(self, path):
        if Path(path).is_symlink():
            raise ValueError('作品目录不能是符号链接')
        path = Path(path).resolve()
        roots = [self.user_data / 'episodes', self.output_root]
        if path.is_symlink() or not path.is_dir() or not any(
                r.resolve() in path.parents for r in roots):
            raise ValueError('作品必须位于当前账号的作品目录内')
        meta = load_meta(path)
        if meta.account_id and meta.account_id != self.account_id:
            raise ValueError('作品所属账号与当前账号不一致')
        meta.account_id, meta.account_label = self.account_id, self.account_label
        meta.work_id = self._identity(meta, path)
        return path, meta

    def describe_source(self, path):
        """Portable metadata plus explicitly referenced source files for export."""
        path, meta = self._source(path)
        metadata = meta.to_dict()
        metadata.update(kind='episode', legacy_name=self.state['paths'].get(
            str(path), {}).get('legacy_name', path.name))
        extra = {}
        for field in ('cover_custom', 'banner_custom', 'icon_custom'):
            if not metadata.get(field):
                continue
            p = Path(metadata[field])
            if not p.is_absolute():
                p = path / p
            try:
                logical = p.resolve().relative_to(path).as_posix()
            except ValueError:
                logical = '_external/' + field + p.suffix.lower()
            extra[logical] = str(p)
            metadata[field] = logical
        return {'path': str(path), 'account_id': self.account_id,
                'work_id': meta.work_id, 'metadata': metadata,
                'extra_files': extra}

    def capture(self, path):
        self.require_account()
        path, meta = self._source(path)
        if load_meta(path).to_dict() != meta.to_dict():
            save_meta(path, meta)  # Persist a new UUID only once, not on refresh.
        source = self.describe_source(path)
        library = self.library
        files = {}
        for item in sorted(path.rglob('*')):
            rel = item.relative_to(path).as_posix()
            if rel == 'meta.json' or is_private(rel):
                continue
            if item.is_symlink():
                raise ValueError(f'资源包含符号链接，请先复制实际文件：{rel}')
            if item.is_file():
                files[rel] = library.put_file(item)
        missing = []
        for logical, external in source['extra_files'].items():
            if Path(external).is_file() and not Path(external).is_symlink():
                files[logical] = library.put_file(external)
            else:
                missing.append(logical)
        metadata = source['metadata']
        metadata['resource_placeholder'] = not bool(files)
        metadata['missing_resources'] = missing
        digest = fingerprint(metadata, files)
        marker = self.state['paths'].get(str(path), {})
        if marker.get('fingerprint') == digest and marker.get('revision_id'):
            return {'work_id': meta.work_id, 'revision_id': marker['revision_id']}
        parents = [marker['revision_id']] if marker.get('revision_id') else []
        current = library.read_work(self.account_id, meta.work_id)
        # A new local resource may replace only a sole resource-free placeholder.
        if not parents and current.get('revision') and current['state'] == 'placeholder':
            parents = [current['revision']['revision_id']]
        rev = library.write_revision(self.account_id, meta.work_id, metadata, files,
                                     parents=parents)
        meta.resource_placeholder = not bool(files)
        if load_meta(path).to_dict() != meta.to_dict():
            save_meta(path, meta)
        self.state['paths'][str(path)] = {'work_id': meta.work_id,
            'account_id': self.account_id, 'revision_id': rev['revision_id'],
            'fingerprint': digest, 'legacy_name': metadata['legacy_name']}
        self.save()
        return {'work_id': meta.work_id, 'revision_id': rev['revision_id']}

    def capture_all(self):
        if not self.enabled:
            return
        roots = [self.output_root]
        if not self.state.get('root'):
            roots.append(self.user_data / 'episodes')
        for root in roots:
            for path in sorted(root.glob('episode*')):
                if path.is_dir() and load_meta(path).account_id in ('', self.account_id):
                    # Old unbound directories require explicit binding first.
                    if root == self.user_data / 'episodes' and not load_meta(path).account_id:
                        continue
                    self.capture(path)
        result = SharedSettings(self).capture()
        self._record_settings_result(result)
        return result

    def path_for(self, work_id):
        root = self.output_root
        known = [Path(p) for p, marker in self.state['paths'].items()
                 if marker.get('work_id') == work_id and Path(p).parent == root
                 and Path(p).is_dir()]
        return sorted(known)[0] if known else root / ('episode_' + work_id)

    def _materialize(self, work):
        revision = work.get('revision')
        if (not revision or work['state'] not in ('available', 'placeholder')
                or work.get('sync_conflicts')):
            return
        wid = work['work_id']
        target = self.path_for(wid)
        marker = self.state['paths'].get(str(target), {})
        if marker.get('revision_id') == revision['revision_id'] and target.is_dir():
            return
        def can_replace_projection():
            if target.is_dir():
                captured = self.capture(target)
                if captured['work_id'] != wid:
                    raise ValueError('目标目录包含其他作品，已保留本地文件')
            current = self.library.read_work(self.account_id, wid)
            return (current.get('state') in ('available', 'placeholder') and
                    (current.get('revision') or {}).get('revision_id') == revision['revision_id'])
        # Even capture=False callers must preserve edits before replacing a
        # projection.  Offline edits become a branch of their actual parent.
        if not can_replace_projection():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # Stage beside the destination.  A connected workspace may live on a
        # different volume from device state, where rename() would otherwise
        # fail with EXDEV after a successful materialization.
        stage = target.parent / ('.staging-' + uuid.uuid4().hex)
        old = target.parent / ('.previous-' + uuid.uuid4().hex)
        replaced = False
        try:
            self.library.materialize(self.account_id, wid, stage, revision['revision_id'])
            meta = EpisodeMeta.from_dict(revision['metadata'])
            meta.work_id, meta.account_id = wid, self.account_id
            meta.account_label = self.account_label
            for field in ('cover_custom', 'banner_custom', 'icon_custom'):
                if getattr(meta, field):
                    setattr(meta, field, str(target / getattr(meta, field)))
            save_meta(stage, meta)
            # Copying large resources can take time.  Check again before the
            # swap in case the user edited the open folder during that copy.
            if not can_replace_projection():
                return
            if target.exists() or target.is_symlink():
                if target.is_symlink():
                    raise ValueError('作品目标目录不能是符号链接')
                target.rename(old)
                replaced = True
            stage.rename(target)
            if old.exists():
                shutil.rmtree(old)
            self.state['paths'][str(target)] = {'work_id': wid, 'account_id': self.account_id,
                'revision_id': revision['revision_id'],
                'legacy_name': revision['metadata'].get('legacy_name', target.name),
                'fingerprint': fingerprint(revision['metadata'], revision['files'])}
            self.save()
        except Exception:
            if replaced and old.exists() and not target.exists():
                old.rename(target)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            if old.exists() and target.exists():
                shutil.rmtree(old, ignore_errors=True)

    def _record_settings_result(self, result):
        if not isinstance(result, dict):
            return
        missing = list(self.state.get('settings_seed_missing') or [])
        missing.extend(result.get('missing') or [])
        self.state['settings_diagnostics'] = {
            'conflicts': list(result.get('conflicts') or []),
            'missing': missing,
            'applied': int(result.get('applied') or 0),
            'unchanged': int(result.get('unchanged') or 0),
            'captured': int(result.get('captured') or 0),
            'deferred': int(result.get('deferred') or 0),
            'tombstones': list(result.get('tombstones') or []),
        }
        self.save()

    def refresh(self, capture=True):
        if not self.enabled:
            return self.status()
        try:
            # Probe before capture so a missing connected mount cannot cause
            # any fallback library or empty local placeholder to be created.
            self.library
            if capture:
                self.capture_all()
            self._reconcile_platform_identities()
            for work in self.works():
                self._materialize(work)
            settings_result = SharedSettings(self).apply()
            self._record_settings_result(settings_result)
            self.state.pop('offline_error', None)
            self.save()
        except (FileNotFoundError, OSError, ValueError) as exc:
            # ValueError also covers a changed library identity.  Keep the
            # last known materialized snapshot and surface the problem in
            # status; never recreate a connected catalog automatically.
            if self.state.get('root'):
                self.state['offline_error'] = str(exc)
                self.save()
                return self.status()
            raise
        return self.status()

    def connect(self, path):
        self.require_account()
        destination = ResourceLibrary(Path(path).resolve())
        previous = copy.deepcopy(self.state)
        self.capture_all()
        if destination.root != self.library.root:
            destination.merge_from(self.library)
        self.state.update(root=str(destination.root), library_id=destination.library_id,
            workspace_base=str(destination.root.parent / '.sticker-maker-workspaces' / self.state['device_id']))
        self.save()
        try:
            self.refresh(capture=False)
        except Exception:
            self.state = previous
            self._library_cache = None
            self._library_cache_root = None
            self.save()
            raise
        return self.status()

    def rows(self):
        try:
            self.library
        except (FileNotFoundError, OSError, ValueError) as exc:
            cached = copy.deepcopy(self.state.get('last_rows') or [])
            for row in cached:
                row.update(resource_state='offline', can_edit=False,
                           can_publish=False, can_shelf=False, offline=True,
                           warning=f'资源库当前不可用：{exc}')
            return cached
        rows = []
        for work in self.works():
            if work['state'] == 'deleted' or work['work_id'] in self.state['hidden']:
                continue
            revision = work.get('revision') or (work.get('heads') or [{}])[0]
            metadata = revision.get('metadata', {})
            path = self.path_for(work['work_id'])
            has_sync_conflicts = bool(work.get('sync_conflicts'))
            has_identity_conflict = work['work_id'] in set(self.state.get('identity_conflicts') or [])
            ready = (work['state'] == 'available' and not has_sync_conflicts
                     and not has_identity_conflict
                     and not metadata.get('missing_resources'))
            finals = list((path / '最终版').glob('*.png')) if ready else []
            cover = path / '封面/封面.png'
            if not cover.exists():
                cover = finals[0] if finals else None
            # Publisher remains responsible for exact format/dimension checks.
            required = ['横幅/横幅.png', '封面/封面.png', '图标/图标.png', 'meaning_map.json', '介绍.txt']
            upload = ready and len(finals) >= 8 and all((path / p).is_file() for p in required)
            rows.append(dict(metadata, name=path.name, path=str(path),
                work_id=work['work_id'], account_id=self.account_id,
                resource_state=('conflict' if (has_sync_conflicts or has_identity_conflict) else work['state']),
                can_edit=ready, can_publish=upload,
                can_shelf=(not has_sync_conflicts and not has_identity_conflict
                           and work['state'] not in ('pending', 'conflict') and
                           metadata.get('platform_status') == '审核通过'),
                sticker_count=len(finals), cover=str(cover) if cover else '',
                complete=bool(finals), missing=work.get('missing', []) or metadata.get('missing_resources', []),
                sync_conflicts=work.get('sync_conflicts', []),
                identity_conflict=has_identity_conflict))
        self.state['last_rows'] = copy.deepcopy(rows)
        self.save()
        return rows

    def status(self):
        counts = dict.fromkeys(('available', 'placeholder', 'pending', 'conflict', 'deleted'), 0)
        conflicts, deleted = [], []
        settings_conflicts, settings_missing, warnings = [], [], []
        identity_conflict_ids = set(self.state.get('identity_conflicts') or [])
        accounts = dict(self.state['accounts'])
        lib = None
        offline_error = None
        if self.enabled:
            try:
                lib = self.library
            except (FileNotFoundError, OSError, ValueError) as exc:
                offline_error = str(exc)
                warnings.append({'kind': 'library', 'message': f'资源库当前不可用：{exc}'})
        if lib:
            for work in lib.list_works():
                rev = work.get('revision') or (work.get('heads') or [{}])[0]
                meta = rev.get('metadata', {})
                accounts.setdefault(work['account_id'], meta.get('account_label', work['account_id']))
                if work['account_id'] != self.account_id:
                    continue
                if meta.get('kind', 'episode') == 'settings':
                    setting_item = dict(work, setting_type=meta.get('setting_type', ''),
                                        logical_path=meta.get('logical_path', ''))
                    if work['state'] == 'conflict':
                        settings_conflicts.append(setting_item)
                    elif work['state'] == 'pending':
                        settings_missing.append({'work_id': work['work_id'],
                                                 'missing': work.get('missing', [])})
                    continue
                # Placeholder history collapsed into a resource-backed work is
                # represented by a deleted alias tombstone.  It is an
                # implementation detail, not a user-facing deleted work that
                # can be restored into a duplicate platform binding.
                if work['state'] == 'deleted' and meta.get('identity_alias'):
                    continue
                state = work['state']
                if state == 'available' and work['work_id'] in identity_conflict_ids:
                    # Rows are non-editable for this duplicate binding, so
                    # expose the same state in aggregate counts as well.
                    counts['available'] = max(0, counts.get('available', 0) - 1)
                    state = 'conflict'
                counts[state] = counts.get(state, 0) + 1
                item = dict(work, state=state,
                            album_name=meta.get('album_name', work['work_id']))
                if state == 'conflict': conflicts.append(item)
                if work['state'] == 'deleted': deleted.append(item)
                if work.get('sync_conflicts'):
                    warnings.append({'kind': 'sync_conflict', 'work_id': work['work_id'],
                                     'paths': list(work['sync_conflicts'])})
        # Preserve the latest local settings diagnostics even when a peer has
        # not yet delivered all objects.  Catalog-derived entries above win.
        diagnostics = self.state.get('settings_diagnostics') or {}
        for value in diagnostics.get('conflicts', []) or []:
            if not any(item.get('work_id') == value for item in settings_conflicts):
                settings_conflicts.append({'work_id': value, 'state': 'conflict'})
        for value in diagnostics.get('missing', []) or []:
            if value not in settings_missing:
                settings_missing.append(value)
        # Identity conflicts are catalog-level duplicate bindings even though
        # each individual work may have only one revision head.  Surface them
        # as ordinary conflict cards so the desktop UI can show the heads and
        # guide the user to keep one binding (or make a draft) before publish.
        if lib:
            for work_id in self.state.get('identity_conflicts') or []:
                try:
                    work = lib.read_work(self.account_id, work_id)
                except (FileNotFoundError, OSError, ValueError):
                    continue
                if work.get('state') == 'deleted':
                    continue
                revision = work.get('revision') or (work.get('heads') or [{}])[0]
                metadata = revision.get('metadata', {})
                card = dict(work, album_name=metadata.get('album_name', work_id),
                            identity_conflict=True,
                            conflict_reason='同一平台作品存在多个资源版本，请先共享删除重复绑定或另存为草稿')
                if not any(item.get('work_id') == work_id for item in conflicts):
                    conflicts.append(card)
        for work_id in self.state.get('identity_conflicts') or []:
            warnings.append({'kind': 'identity_conflict', 'work_id': work_id,
                             'message': '同一平台作品存在多个资源版本，请先人工确认'})
        from .transfer import TransferManager
        from .operations import unresolved
        tasks = TransferManager(self.local / 'transfers').tasks()
        for task in tasks:
            cache_plan = self.local / 'cache_plans' / (task['plan_id'] + '.json')
            if cache_plan.exists():
                cleanup = read_json(cache_plan)
                if cleanup.get('errors'):
                    task.update(state='cleanup_partial', errors=cleanup['errors'])
        try:
            unresolved_operations = unresolved(self) if lib else copy.deepcopy(
                (self.state.get('last_status') or {}).get('unresolved_operations', []))
        except (FileNotFoundError, OSError, ValueError):
            unresolved_operations = copy.deepcopy(
                (self.state.get('last_status') or {}).get('unresolved_operations', []))
        result = {'connected': bool(self.state.get('root')), 'available': offline_error is None,
            'offline': offline_error is not None,
            'root': str(lib.root) if lib else str(self.state.get('root') or ''),
            'workspace_path': str(self.output_root) if self.enabled else '',
            'library_id': lib.library_id if lib else self.state.get('library_id', ''),
            'account_id': self.account_id, 'account_label': self.account_label,
            'counts': counts, 'conflicts': conflicts, 'settings_conflicts': settings_conflicts,
            'settings_missing': settings_missing, 'deleted': deleted,
            'unresolved_operations': unresolved_operations,
            'accounts': [{'account_id': k, 'account_label': v}
                                            for k, v in accounts.items()],
            'tasks': tasks, 'warnings': warnings,
            'settings_sync': copy.deepcopy(diagnostics)}
        if offline_error:
            cached = self.state.get('last_status') or {}
            # Counts and conflict snapshots remain useful while offline; all
            # editing/upload gates are enforced by rows(), which is disabled.
            for key in ('counts', 'conflicts', 'settings_conflicts', 'settings_missing',
                        'deleted', 'accounts'):
                if cached.get(key) is not None:
                    result[key] = copy.deepcopy(cached[key])
        self.state['last_status'] = copy.deepcopy(result)
        if offline_error:
            self.state['offline_error'] = offline_error
        else:
            self.state.pop('offline_error', None)
        self.save()
        return result

    def delete(self, work_id, action):
        work = self.library.read_work(self.account_id, work_id)
        if not work.get('heads'):
            raise ValueError('作品不存在')
        if action == 'hide':
            if work_id not in self.state['hidden']:
                self.state['hidden'].append(work_id)
            self.save()
        elif action in ('delete', 'restore'):
            if work['state'] == 'conflict':
                raise ValueError('请先处理作品版本冲突')
            rev = work.get('revision') or work['heads'][0]
            self.library.write_revision(self.account_id, work_id, rev['metadata'], rev['files'],
                parents=[r['revision_id'] for r in work['heads']], deleted=action == 'delete')
            if action == 'restore' and work_id in self.state['hidden']:
                self.state['hidden'].remove(work_id); self.save()
        else:
            raise ValueError('不支持的删除操作')
        return self.refresh(capture=False)

    def resolve(self, work_id, revision_id, action='choose'):
        work = self.library.read_work(self.account_id, work_id)
        candidates = list(work.get('heads') or [])
        selected = next((r for r in candidates if r.get('revision_id') == revision_id), None)
        is_settings = any(r.get('metadata', {}).get('kind') == 'settings' for r in candidates)
        if is_settings and action == 'draft':
            raise ValueError('设置冲突只能选择版本，不能另存为作品草稿')
        if action == 'draft':
            rev = selected
            if not rev:
                raise ValueError('请选择有效冲突版本')
            meta = dict(rev['metadata'])
            for key in list(meta):
                if key.startswith('platform_'): meta.pop(key)
            wid = uuid.uuid4().hex
            meta.update(work_id=wid, published=False, published_at='', number=None,
                        series_id=None, series_name='', album_name=meta.get('album_name', '') + '副本')
            self.library.write_revision(self.account_id, wid, meta, rev['files'], parents=[])
        elif action == 'choose':
            if not selected:
                raise ValueError('请选择有效冲突版本')
            self.library.resolve(self.account_id, work_id, revision_id)
        else:
            raise ValueError('未知版本处理方式')
        return self.refresh(capture=False)


def active_runtime():
    from ..config.paths import resolve_paths, current_platform
    return LibraryRuntime(resolve_paths(current_platform()).user_data)
