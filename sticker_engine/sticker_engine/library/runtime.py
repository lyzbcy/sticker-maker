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
import threading
from pathlib import Path
from ..media import final_stickers, sticker_type

from ..config.series import EpisodeMeta, load_meta, save_meta
from ..publish.platform_data import SHELFABLE_STATUSES
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
            # Device state is a large private snapshot, not a hand-edited file.
            # One compact C-encoder write avoids hundreds of thousands of
            # Python encoder/write calls per marker update. Durability and
            # atomic replacement remain immediate on EVERY save.
            f.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
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


def _content_fingerprint(metadata, files):
    """Directory-name-agnostic fingerprint: identical episode content must
    compare equal after a materialization renamed episode_<timestamp> to
    episode_<work_id> (legacy_name is a projection detail, not content)."""
    from .reconciliation import authored_metadata
    normalized = authored_metadata(metadata or {})
    return fingerprint(normalized, files)


def _content_equivalent_in_history(library, account_id, work_id, head, metadata, files):
    """True when the local capture has no substantive divergence from the
    current head or any of its ancestors (identical files and metadata except
    legacy_name).  Single-head works only: a conflicted work stays visible."""
    local = _content_fingerprint(metadata, files)

    def _fp(revision):
        return _content_fingerprint(revision.get('metadata') or {},
                                    revision.get('files') or {})

    if _fp(head) == local:
        return True
    by_id = {r['revision_id']: r for r in library.revisions(account_id, work_id)}
    stack, seen = list(head.get('parents') or []), set()
    while stack:
        revision_id = stack.pop()
        if revision_id in seen or revision_id not in by_id:
            continue
        seen.add(revision_id)
        revision = by_id[revision_id]
        if _fp(revision) == local:
            return True
        stack.extend(revision.get('parents') or [])
    return False


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
            self._rows_at = 0
            self._refresh_cache = None
            self.state['last_rows'] = []
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
        result = self.status()
        import time as _time
        self._refresh_cache = {"at": _time.monotonic(), "status": result}
        return result

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
            # 2026-09-12 修复：同 work 的投影目录常缺 platform_item_id
            # （旧投影生成时不带），复用前先补上——否则每次同步都把该
            # 平台行当"未匹配"重走 placeholder（created 虚高 218）
            if (m.account_id == self.account_id and not m.platform_item_id
                    and m.album_name == str(row.get('Name') or '')
                    and self.library.read_work(self.account_id, m.work_id or '')
                    .get('revision', {}).get('metadata', {}).get('platform_item_id') == sid):
                m.platform_item_id = sid
                save_meta(p, m)
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
        # Device-local platform observations are not artwork edits. When the
        # local fields still equal our observation, compare/capture the parent's
        # original platform fields; otherwise a later capture would manufacture
        # a third asset head solely because the platform status was refreshed.
        observation = self.state.get('platform_observations', {}).get(self.account_id + '/' + meta.work_id)
        parent_id = self.state['paths'].get(str(path), {}).get('revision_id')
        if observation and parent_id and all(metadata.get(k) == v for k, v in observation.items()):
            parent = next((r for r in library.revisions(self.account_id, meta.work_id)
                           if r['revision_id'] == parent_id), None)
            if parent:
                for key in observation:
                    if key in parent['metadata']:
                        metadata[key] = copy.deepcopy(parent['metadata'][key])
                    else:
                        metadata.pop(key, None)
        digest = fingerprint(metadata, files)
        marker = self.state['paths'].get(str(path), {})
        if marker.get('fingerprint') == digest and marker.get('revision_id'):
            return {'work_id': meta.work_id, 'revision_id': marker['revision_id']}
        current = library.read_work(self.account_id, meta.work_id)
        # 2026-09-09 分叉根修：本地内容若已包含在当前任一 head 里（head
        # 被 resolve/合并推进而本地没再改），直接跟随该 head 并更新
        # marker——旧实现拿过期 marker 当父会写出平行分支（一次同步
        # 281 个作品全冲突）。指纹与所有 head 都不同 = 本地与远端真实
        # 分歧，仍走显式分支让用户选（不静默合并覆盖，测试保障的语义）。
        for head in (current.get('heads') or []):
            if fingerprint(head.get('metadata') or {}, head.get('files') or {}) == digest:
                self.state['paths'][str(path)] = {'work_id': meta.work_id,
                    'account_id': self.account_id, 'revision_id': head['revision_id'],
                    'fingerprint': digest, 'legacy_name': metadata['legacy_name']}
                self.save()
                return {'work_id': meta.work_id, 'revision_id': head['revision_id']}
        # 2026-09-10 批量发布 40 作品分叉根因：fingerprint 把 legacy_name
        # （目录名，非内容）算进哈希——作品目录从时间戳名（生成流水线产出）
        # 物化为 episode_<work_id> 名后，同一内容的指纹必然漂移；并发实例
        # （发布进程与引擎单例各持内存 state）中缺少该路径 marker 的一方
        # 走到下面就会 write_revision(parents=[]) 写出内容等价的孤儿根，
        # 双 head 冲突。本地内容与库无实质分歧（剔除 legacy_name 后与当前
        # head 或其祖先完全一致）时跟随现有 head 并 fast-forward marker，
        # 绝不写平行修订；文件或实质字段不同 = 真实分歧，仍走显式分支。
        heads = current.get('heads') or []
        if len(heads) == 1 and _content_equivalent_in_history(
                library, self.account_id, meta.work_id, heads[0], metadata, files):
            self.state['paths'][str(path)] = {'work_id': meta.work_id,
                'account_id': self.account_id, 'revision_id': heads[0]['revision_id'],
                'fingerprint': digest, 'legacy_name': metadata['legacy_name']}
            self.save()
            return {'work_id': meta.work_id, 'revision_id': heads[0]['revision_id']}
        parents = [marker['revision_id']] if marker.get('revision_id') else []
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
        self._rows_at = 0   # 新作品/新内容入库：rows 快照立即失效
        return {'work_id': meta.work_id, 'revision_id': rev['revision_id']}

    def commit_platform_metadata(self, path, meta):
        """Commit only platform observations; never hash/copy artwork for sync.

        Require the projection's exact parent and retain its existing file map.
        A changed/shared head is not silently adopted. The caller keeps LOCK,
        persists device markers once in finally, and reports any per-work error.
        """
        self.require_account()
        path = Path(path)
        if meta.account_id != self.account_id or not meta.work_id:
            raise ValueError('平台状态入库账号或作品身份不一致')
        marker = self.state['paths'].get(str(path), {})
        work = self.library.read_work(self.account_id, meta.work_id)
        revision = work.get('revision')
        observations = {key: copy.deepcopy(value) for key, value in meta.to_dict().items()
                        if key.startswith('platform_') or key == 'published'}
        if not hasattr(self, '_platform_row_updates'):
            self._platform_row_updates = {}
        observation_key = self.account_id + '/' + meta.work_id
        if (work['state'] == 'conflict' or work.get('sync_conflicts')
                or meta.work_id in self.state.get('identity_conflicts', [])):
            # Platform facts can be refreshed even while artwork heads conflict.
            # Keep them as device-local observations, NOT a merged asset revision.
            self.state.setdefault('platform_observations', {})[observation_key] = observations
            self._platform_row_updates[meta.work_id] = observations
            if not hasattr(self, '_platform_conflicted_updates'):
                self._platform_conflicted_updates = set()
            self._platform_conflicted_updates.add(meta.work_id)
            return
        if not revision and not work.get('heads') and not work.get('sync_conflicts'):
            # A brand-new platform placeholder has no parent/file map yet.
            # Capture just this new work once (normally meta.json only), not
            # the whole library; the standard capture path validates its roots.
            self.capture(path)
            self._platform_row_updates[meta.work_id] = observations
            return
        if (not revision or work['state'] not in ('available', 'placeholder')
                or work.get('sync_conflicts')
                or marker.get('revision_id') != revision['revision_id']
                or meta.work_id in self.state.get('identity_conflicts', [])):
            raise ValueError('作品资源库版本已变更或存在冲突，已保留本地平台结果')
        metadata = copy.deepcopy(revision['metadata'])
        metadata.update(observations)
        if all(key == 'platform_updated_at' or value == revision['metadata'].get(key)
               for key, value in observations.items()):
            # A new check time is not a new shared artwork revision. Keep the
            # observation locally; publish a revision only for changed facts.
            self.state.setdefault('platform_observations', {})[observation_key] = observations
            self._platform_row_updates[meta.work_id] = observations
            return
        if metadata == revision['metadata']:
            self._platform_row_updates[meta.work_id] = observations
            return
        files = revision.get('files') or {}
        updated = self.library.write_revision(
            self.account_id, meta.work_id, metadata, files,
            parents=[revision['revision_id']])
        self.state['paths'][str(path)] = dict(marker,
            revision_id=updated['revision_id'], fingerprint=fingerprint(metadata, files))
        self.state.setdefault('platform_observations', {}).pop(observation_key, None)
        self._platform_row_updates[meta.work_id] = observations
        # A work can have both timestamp and work-id projections. Keep platform
        # observations aligned across siblings of the same parent; otherwise a
        # later full capture mistakes the old sibling's status for an offline edit.
        for sibling, sibling_marker in list(self.state['paths'].items()):
            sibling_path = Path(sibling)
            if (sibling == str(path) or sibling_marker.get('work_id') != meta.work_id
                    or sibling_marker.get('revision_id') != revision['revision_id']
                    or sibling_path.parent != self.output_root
                    or not sibling_path.is_dir() or sibling_path.is_symlink()):
                continue
            sibling_meta = load_meta(sibling_path)
            if sibling_meta.work_id != meta.work_id or sibling_meta.account_id != self.account_id:
                continue
            for key, value in observations.items():
                if key.startswith('platform_') or key == 'published':
                    setattr(sibling_meta, key, copy.deepcopy(value))
            save_meta(sibling_path, sibling_meta)
            self.state['paths'][sibling] = dict(sibling_marker,
                revision_id=updated['revision_id'], fingerprint=fingerprint(metadata, files))
        self._rows_at = 0
        self._refresh_cache = None

    def finish_platform_sync(self):
        """Update the existing row snapshot without re-enumerating all artwork."""
        updates = getattr(self, '_platform_row_updates', {})
        cached = self.state.get('last_rows')
        if cached is not None:
            known = {r.get('work_id') for r in cached}
            if set(updates) <= known:
                for row in cached:
                    observations = updates.get(row.get('work_id'))
                    if observations is None:
                        continue
                    row.update(copy.deepcopy(observations))
                    if row.get('work_id') in getattr(self, '_platform_conflicted_updates', set()):
                        row.update(resource_state='conflict', can_edit=False, can_publish=False)
                    row['can_shelf'] = (row.get('resource_state') in ('available', 'placeholder')
                        and not row.get('offline')
                        and not row.get('sync_conflicts') and not row.get('identity_conflict')
                        and row.get('platform_status') in SHELFABLE_STATUSES)
                self._rows_at = __import__('time').monotonic()
            else:
                self._rows_at = 0
        self._platform_row_updates = {}
        self._platform_conflicted_updates = set()
        self.save()

    def _platform_metadata(self, work_id, metadata):
        """Overlay same-account observations without resolving resource conflicts."""
        observation = self.state.get('platform_observations', {}).get(self.account_id + '/' + work_id)
        if (observation and (not metadata.get('platform_item_id') or
                metadata.get('platform_item_id') == observation.get('platform_item_id'))
                and str(observation.get('platform_updated_at', '')) >= str(metadata.get('platform_updated_at', ''))):
            return dict(metadata, **copy.deepcopy(observation))
        return metadata

    def capture_all(self):
        if not self.enabled:
            return
        # 2026-09-05 性能：轻快照（文件名+mtime+size 清单）与上次一致且上次
        # 捕获成功 → 跳过该目录的逐文件 SHA-256（未变更的 340 单每次 refresh
        # 被全量哈希两遍是 refresh 140s 的主要构成）。内容变化必然改 mtime。
        # 2026-09-11 性能：快照扫描改线程池并行——450 目录×60 文件的 ~3 万次
        # stat 是批量发布每弹 hooks 前后刷新里最大的隐形耗时（实测 ~74s/弹），
        # stat 是 IO 型，8 线程立省大半。shared 状态只读，各目录独立。
        light = self.state.get('capture_light') or {}
        import time as _time
        from concurrent.futures import ThreadPoolExecutor
        from .reconciliation import authored_metadata
        started = _time.monotonic()

        def report(phase, completed, total, label):
            callback = getattr(self, '_progress_callback', None)
            if callback:
                try:
                    callback({'phase': phase, 'completed': completed, 'total': total,
                              'elapsed_seconds': round(_time.monotonic()-started, 2),
                              'message': f'{label} {completed}/{total}'})
                except Exception:
                    pass

        def _snap_one(path):
            try:
                meta = load_meta(path)
                if not (path.is_dir() and meta.account_id in ('', self.account_id)):
                    return None
                # Old unbound directories require explicit binding first.
                if path.parent == self.user_data / 'episodes' and not load_meta(path).account_id:
                    return None
                snapshot = sorted(
                    (f.relative_to(path).as_posix(), f.stat().st_mtime_ns, f.stat().st_size)
                    for f in path.rglob('*') if f.is_file()
                    and f != path / 'meta.json' and not is_private(path / f.relative_to(path)))
                # A changed check-time/status is not a changed illustration.
                # Keep authored metadata AND platform identity in the light key;
                # changing a name/cover/ID still forces full capture.
                external = []
                for field in ('cover_custom', 'banner_custom', 'icon_custom'):
                    if getattr(meta, field):
                        file = Path(getattr(meta, field))
                        if not file.is_absolute(): file = path / file
                        stat = file.stat() if file.is_file() else None
                        external.append((field, str(file), stat.st_mtime_ns if stat else None,
                                         stat.st_size if stat else None))
                return path, {'v': 2, 'files': snapshot,
                              'metadata': authored_metadata(meta.to_dict()), 'external': external}
            except OSError:
                return None

        light_new = {}
        changed = []   # (path, snapshot_key) 有变更、需要真正 capture 的目录
        roots = [self.output_root]
        if not self.state.get('root'):
            roots.append(self.user_data / 'episodes')
        paths = [path for root in roots for path in sorted(root.glob('episode*'))]
        report('capture_scan', 0, len(paths), '正在扫描资源库轻快照')
        last_report = _time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for index, result in enumerate(pool.map(_snap_one, paths), 1):
                if index % 100 == 0 or index == len(paths) or _time.monotonic()-last_report >= 5:
                    report('capture_scan', index, len(paths), '正在扫描资源库轻快照')
                    last_report = _time.monotonic()
                if result is None:
                    continue
                path, snapshot = result
                key = str(path)
                snapshot_key = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                if light.get(key, {}).get('snapshot') == snapshot_key and light[key].get('captured_at'):
                    light_new[key] = light[key]
                    continue
                changed.append((path, snapshot_key))
        deadline = _time.monotonic() + 100   # 硬上限：真正哈希的总量不超过 ~100s
        for index, (path, snapshot_key) in enumerate(changed, 1):
            if _time.monotonic() > deadline:
                light_new[str(path)] = light.get(str(path), {'captured_at': 0})
                continue   # 超时预算：本轮跳过，下轮补
            self.capture(path)
            light_new[str(path)] = {'snapshot': snapshot_key,
                                    'captured_at': _time.monotonic()}
            if index % 100 == 0 or index == len(changed) or _time.monotonic()-last_report >= 5:
                report('capture_changed', index, len(changed), '正在捕获变更资源')
                last_report = _time.monotonic()
        self.state['capture_light'] = light_new
        self.save()
        result = SharedSettings(self).capture()
        self._record_settings_result(result)
        return result

    def path_for(self, work_id):
        root = self.output_root
        known = [Path(p) for p, marker in self.state['paths'].items()
                 if marker.get('work_id') == work_id and Path(p).parent == root
                 and Path(p).is_dir()]
        return sorted(known)[0] if known else root / ('episode_' + work_id)

    def _work_path_map(self):
        """work_id → 本地已物化目录（str）。rows()/materialize 批量循环用：
        一趟索引替代每作品全表扫描（431 作品 × 500 路径的 Path 解析是
        refresh 26s 的构成，2026-09-10）。语义与 path_for 一致：同名取
        字典序最小、只认 output_root 直下、必须真实存在。"""
        root = self.output_root
        mapping = {}
        for p, marker in (self.state.get('paths') or {}).items():
            wid = marker.get('work_id')
            if not wid or Path(p).parent != root or not Path(p).is_dir():
                continue
            cur = mapping.get(wid)
            if cur is None or p < cur:
                mapping[wid] = p
        return mapping

    def _materialize(self, work, path=None, force=False):
        revision = work.get('revision')
        if (not revision or work['state'] not in ('available', 'placeholder')
                or work.get('sync_conflicts')):
            return
        wid = work['work_id']
        target = Path(path) if path else self.path_for(wid)
        marker = self.state['paths'].get(str(target), {})
        if not force and marker.get('revision_id') == revision['revision_id'] and target.is_dir():
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
            meta = EpisodeMeta.from_dict(self._platform_metadata(wid, revision['metadata']))
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

    def refresh(self, capture=True, max_age=None):
        # 2026-09-05 性能根修：refresh 全量跑一次 ~140s（340 单逐文件哈希），
        # 此前每条命令（含纯读）都持全局锁跑一遍 → 10 个并发请求要 27 分钟。
        # max_age 秒内的调用直接返回缓存快照（读命令容忍 ≤60s 延迟）。
        if max_age is not None:
            cached = getattr(self, "_refresh_cache", None)
            now = __import__("time").monotonic()
            if cached and now - cached["at"] <= max_age:
                return cached["status"]
        if not self.enabled:
            return self.status()
        try:
            # Probe before capture so a missing connected mount cannot cause
            # any fallback library or empty local placeholder to be created.
            self.library
            if capture:
                self.capture_all()
            self._reconcile_platform_identities()
            path_map = self._work_path_map()
            works = self.works()
            callback = getattr(self, '_progress_callback', None)
            start = __import__('time').monotonic()
            reported = start
            for index, work in enumerate(works, 1):
                self._materialize(work, path_map.get(work['work_id']))
                now = __import__('time').monotonic()
                if callback and (index % 100 == 0 or index == len(works) or now-reported >= 5):
                    try:
                        callback({'phase': 'materialize', 'completed': index, 'total': len(works),
                                  'elapsed_seconds': round(now-start, 2),
                                  'message': f'正在对齐共享资源 {index}/{len(works)}'})
                    except Exception:
                        pass
                    reported = now
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
        result = self.status()
        import time as _time
        self._refresh_cache = {"at": _time.monotonic(), "status": result}
        return result

    def connect(self, path):
        self.require_account()
        destination = ResourceLibrary(Path(path).resolve())
        previous = copy.deepcopy(self.state)
        self.capture_all()
        if destination.root != self.library.root:
            destination.merge_from(self.library)
        self.state.update(root=str(destination.root), library_id=destination.library_id,
            workspace_base=str(destination.root.parent / '.sticker-maker-workspaces' / self.state['device_id']))
        self._rows_at = 0
        self._refresh_cache = None
        self.state['last_rows'] = []
        self.save()
        try:
            self.refresh(capture=False)
        except Exception:
            self.state = previous
            self._library_cache = None
            self._library_cache_root = None
            self.save()
            raise
        result = self.status()
        import time as _time
        self._refresh_cache = {"at": _time.monotonic(), "status": result}
        return result

    def rows(self):
        # 2026-09-05 性能：rows 全量扫库 + 306 个作品目录 glob，冷跑 ~20s。
        # 30s 内的重复调用直接用快照（runtime 实例已挂 engine 单例复用）。
        # 2026-09-11 用户反馈"每次切换都卡"：TTL 30s→120s；delete/resolve/
        # capture 处已同步打穿（capture 新作品/改动入口，delete/resolve 改
        # 变可见性），发布等校验路径有 hooks 前 refresh 兜底新鲜度。
        import time as _time
        rows_at = getattr(self, '_rows_at', 0)
        if rows_at > 0 and _time.monotonic() - rows_at < 120:
            cached = self.state.get('last_rows')
            if cached is not None:
                return cached
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
        path_map = self._work_path_map()
        for work in self.works():
            if work['state'] == 'deleted' or work['work_id'] in self.state['hidden']:
                continue
            revision = work.get('revision') or (work.get('heads') or [{}])[0]
            metadata = self._platform_metadata(work['work_id'], revision.get('metadata', {}))
            path = Path(path_map.get(work['work_id']) or self.path_for(work['work_id']))
            has_sync_conflicts = bool(work.get('sync_conflicts'))
            has_identity_conflict = work['work_id'] in set(self.state.get('identity_conflicts') or [])
            ready = (work['state'] == 'available' and not has_sync_conflicts
                     and not has_identity_conflict
                     and not metadata.get('missing_resources'))
            finals = final_stickers(path / '最终版') if ready else []
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
                           metadata.get('platform_status') in SHELFABLE_STATUSES),
                sticker_type=sticker_type(finals), sticker_count=len(finals), cover=str(cover) if cover else '',
                complete=bool(finals), missing=work.get('missing', []) or metadata.get('missing_resources', []),
                sync_conflicts=work.get('sync_conflicts', []),
                identity_conflict=has_identity_conflict))
        self.state['last_rows'] = copy.deepcopy(rows)
        self._rows_at = _time.monotonic()
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
                if meta.get('kind', 'episode') != 'episode':
                    # Operation journals are not albums (including tombstones).
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
        # 2026-09-10：hide/delete/restore 改变作品可见性，必须打穿 rows 的
        # 30s 快照缓存，否则删除后列表 30 秒内仍显示该作品（用户重复点删）。
        self._rows_at = 0
        return self.refresh(capture=False)

    def resolve(self, work_id, revision_id, action='choose', expected_heads=None):
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
        elif action in ('choose', 'choose_keep_ratings'):
            if not selected:
                raise ValueError('请选择有效冲突版本')
            if action == 'choose_keep_ratings':
                from .reconciliation import choose_preserving_ratings
                merged = choose_preserving_ratings(self.library, self.account_id,
                    work_id, revision_id, expected_heads)
            else:
                merged = self.library.resolve(self.account_id, work_id, revision_id)
            if is_settings:
                # resolve 后立即把选定的设置版本物化到本地：本地旧内容 +
                # 过期 marker 会让下一次 apply 误判（unchanged 跳过或再次
                # 冲突），"resolve→同步→又冲突"死循环的另一半（2026-09-09）
                try:
                    from .settings import SharedSettings
                    SharedSettings(self).force_apply_entity(work_id, merged['revision_id'])
                except Exception:   # noqa: BLE001
                    pass   # 物化失败不阻断 resolve 本身，冲突卡仍在可重试
            else:
                # episode 同款对齐（2026-09-12 "清了又长"根因）：resolve
                # 合并了头，但 state['paths'] 的 marker 若仍指向被合并的旧
                # 支，下一次 capture 又从旧支分叉——冲突立即复活（skill
                # 第 4 条教训的 episode 版；settings 走 force_apply_entity，
                # episode 走这里对齐 revision_id，fingerprint 不动——本地
                # 内容没变）。
                if action == 'choose_keep_ratings':
                    # Do not advance a stale projection marker before copying
                    # the chosen artwork: _materialize's marker fast path would
                    # otherwise leave the discarded artwork visible forever.
                    for p, mk in list((self.state.get('paths') or {}).items()):
                        if (isinstance(mk, dict) and mk.get('work_id') == work_id
                                and Path(p).resolve().is_relative_to(self.output_root.resolve())):
                            current = self.library.read_work(self.account_id, work_id)
                            self._materialize(current, Path(p))
                elif merged and merged.get('revision_id'):
                    new_id = merged['revision_id']
                    for p, mk in (self.state.get('paths') or {}).items():
                        if isinstance(mk, dict) and mk.get('work_id') == work_id:
                            mk['revision_id'] = new_id
                    self.save()
        else:
            raise ValueError('未知版本处理方式')
        # 同 delete：resolve 改变冲突/head 状态，rows 快照立即失效
        self._rows_at = 0
        return self.refresh(capture=False)

    def materialize_chosen(self, work_id, revision_id):
        """Resume an interrupted projection swap, never rewrite revision heads.

        An advanced marker alone is not proof that chosen bytes are on disk.
        Force only skips that marker shortcut; capture and exact-head checks
        remain in _materialize, so concurrent authored edits are still preserved.
        """
        self.require_account()
        work = self.library.read_work(self.account_id, work_id)
        if work['state'] != 'available' or work['revision']['revision_id'] != revision_id:
            raise ValueError('素材版本已变化，请重新核验')
        paths = [Path(p) for p, mk in (self.state.get('paths') or {}).items()
                 if isinstance(mk, dict) and mk.get('work_id') == work_id
                 and Path(p).resolve().is_relative_to(self.output_root.resolve())]
        for path in paths or [self.path_for(work_id)]:
            self._materialize(self.library.read_work(self.account_id, work_id), path, force=True)
        self._rows_at = 0
        return self.status()


_ACTIVE_RUNTIME_CACHE = {}
_ACTIVE_RUNTIME_LOCK = threading.RLock()


def runtime_for_user_data(user_data):
    """One state/catalog/refresh cache for every actor on the same device.

    Engine hooks and Publisher used to cache independent instances, allowing
    stale markers to overwrite each other and duplicating expensive refreshes.
    Explicit LibraryRuntime(...) instances remain available for peer fixtures.
    """
    data = Path(user_data).expanduser().resolve()
    key = os.path.normcase(str(data))
    with _ACTIVE_RUNTIME_LOCK:
        rt = _ACTIVE_RUNTIME_CACHE.get(key)
        disk = read_json(data / "resource_library" / "device.json")
        direct = disk.get("storage_mode") == "projects"
        if rt is None or (rt.__class__.__name__ == "ProjectRuntime") != direct:
            if direct:
                from .projects import ProjectRuntime
                rt = ProjectRuntime(data)
            else:
                rt = LibraryRuntime(data)
            _ACTIVE_RUNTIME_CACHE[key] = rt
        return rt


def active_runtime():
    """2026-09-11 性能根修：进程内按 user_data 记忆化 runtime 单例。

    此前每次调用 new 一个实例——catalog 解析缓存（_work_cache）、rows
    30s 快照、refresh TTL 全部随实例丢弃，批量发布路径每弹都要付
    ~80s 冷解析（runtime_for 在 2026-09-05 已做同款修复，这里补齐）。
    账号变更命令走 cli._engine=None → hooks.runtime_for 重建，本缓存
    服务的是发布/补发等直接调用方，进程生命周期内账号不变。
    """
    from ..config.paths import resolve_paths, current_platform
    return runtime_for_user_data(resolve_paths(current_platform()).user_data)
