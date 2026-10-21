"""Self-contained, named projects. No object store or materialized copies.

Existing Chinese asset directory names remain the on-disk format so old engines,
exports and artists' files can be imported losslessly. project.json owns identity,
meanings, character information and the manifest; rating.json owns human ratings.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

FORMAT = 'sticker-maker-project'
SCHEMA = 1
_LOCK = threading.RLock()
_HELD = threading.local()
ASSET_DIRS = {'最终版', '封面', '横幅', '图标', '赞赏图'}
SOURCE_DIRS = {'原图', '参考图'}


def chinese_number(number):
    n = int(number)
    if not 0 < n < 10000:
        return str(n)
    digits = '零一二三四五六七八九'
    text = ''
    zero = False
    for unit, label in ((1000, '千'), (100, '百'), (10, '十'), (1, '')):
        value, n = divmod(n, unit)
        if value:
            if zero:
                text += '零'
            text += digits[value] + label
            zero = False
        elif text and n:
            zero = True
    return text[1:] if text.startswith('一十') else text


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_project(directory):
    path = Path(directory) / 'project.json'
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError('工程清单不能是符号链接')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('format') != FORMAT or data.get('schema_version') != SCHEMA:
        raise ValueError('工程格式或版本不受支持，请升级软件')
    if not isinstance(data.get('metadata'), dict) or not data['metadata'].get('work_id'):
        raise ValueError('工程缺少作品身份')
    if data.get('mode') not in ('full', 'delivery'):
        raise ValueError('工程模式无效')
    if not isinstance(data.get('files', {}), dict):
        raise ValueError('工程文件清单无效')
    for logical in data.get('files', {}):
        safe_file(directory, logical)
    return data


def safe_file(directory, logical):
    from .library.resources import validate_logical_path
    logical = validate_logical_path(logical)
    root = Path(directory).resolve()
    path = root / logical
    if not path.resolve().is_relative_to(root) or any(
            p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
            for p in [path, *path.parents] if p == root or root in p.parents):
        raise ValueError('工程文件路径越界或包含链接')
    return path


@contextmanager
def project_lock(directory):
    """Cross-process OS lock; stale lock *files* do not strand an editable project."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('工程目录不存在或是链接')
    lock_path = root / '.project.lock'
    if lock_path.is_symlink():
        raise ValueError('工程锁不能是链接')
    with _LOCK:
        held = getattr(_HELD,'paths',None)
        if held is None:
            held = _HELD.paths = set()
        key = os.path.normcase(str(root.resolve()))
        if key in held:
            yield
            return
        with _os_project_lock(root,lock_path):
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)


@contextmanager
def _os_project_lock(root,lock_path):
    with lock_path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('该工程正在被其他进程修改') from exc
        try:
            if any(root.rglob('*.sync-conflict-*')):
                raise ValueError('工程含同步冲突文件，请处理后继续')
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def update_project(directory, update, expected_revision=None):
    with project_lock(directory):
        data = read_project(directory)
        if data is None:
            raise ValueError('不是规范工程')
        if expected_revision and data.get('revision_id') != expected_revision:
            raise ValueError('工程已变化，请重新读取或生成预览')
        new = copy.deepcopy(data)
        update(new)
        if new != data:
            new['revision_id'] = uuid.uuid4().hex
            atomic_json(Path(directory) / 'project.json', new)
        return new


def folder_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '＿', str(name or '').strip()).rstrip(' .')
    if not name or name in ('.', '..'):
        name = '未命名表情'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', name, re.I):
        name = '_' + name
    return name[:100]


def named_destination(root, name, work_id='', reserved=()):
    root = Path(root)
    base = folder_name(name)
    n = 1
    while True:
        candidate = root / (base if n == 1 else f'{base}（副本{n}）')
        if str(candidate).casefold() in {str(p).casefold() for p in reserved}:
            n += 1; continue
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        if work_id and not candidate.is_symlink():
            existing = read_project(candidate)
            if existing and existing['metadata']['work_id'] == work_id:
                return candidate
        n += 1


def project_directories(root):
    root = Path(root)
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir()) if p.is_dir() and not p.is_symlink()
            and not p.name.startswith('.') and (p / 'project.json').is_file()]


def episode_directories(root):
    """Recognize both legacy episodes and named portable projects."""
    root = Path(root)
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir()) if p.is_dir() and not p.is_symlink()
            and not p.name.startswith('.') and (p.name.startswith('episode')
            or (p / 'project.json').is_file() or (p / 'meta.json').is_file())]


def read_meanings(directory):
    data = read_project(directory)
    if data is not None:
        return data.get('meaning_map', {})
    for logical in ('meaning_map.json', '原图/_meaning_map.json', '原图/meaning_map.json'):
        p = Path(directory) / logical
        if p.is_file():
            return json.loads(p.read_text(encoding='utf-8'))
    return {}


def write_meanings(directory, meanings):
    value = {str(k):v for k,v in meanings.items()}
    if read_project(directory) is not None:
        update_project(directory,lambda d:d.update(meaning_map=value))
    else:
        atomic_json(Path(directory)/'meaning_map.json',value)


def relocate_result(value, old_root, new_root):
    """Keep returned Sticker dataclasses and asset paths valid after renaming."""
    from dataclasses import is_dataclass, fields, replace
    if isinstance(value,Path) and value.is_relative_to(old_root):
        return new_root/value.relative_to(old_root)
    if isinstance(value,list):
        return [relocate_result(v,old_root,new_root) for v in value]
    if isinstance(value,dict):
        return {k:relocate_result(v,old_root,new_root) for k,v in value.items()}
    if is_dataclass(value) and not isinstance(value,type):
        return replace(value,**{f.name:relocate_result(getattr(value,f.name),old_root,new_root)
                                for f in fields(value) if f.init})
    return value


def read_characters(directory):
    data = read_project(directory)
    if data is not None:
        return data.get('characters', [])
    p = Path(directory) / '本次制作角色.md'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.startswith('角色：'):
                return [c for c in line[3:].split('、') if c]
    return []


def require_sources(directory):
    data = read_project(directory)
    if data and data['mode'] == 'delivery':
        raise ValueError('这是精简工程，原图已由用户删除，不能重新裁切、加字或生成素材；请先导入完整工程')


def file_manifest(directory):
    from .library.resources import hash_file
    files = {}
    for p in sorted(Path(directory).rglob('*')):
        rel = p.relative_to(directory).as_posix()
        if rel in ('project.json', '.project.lock') or rel.startswith('.cache/'):
            continue
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise ValueError(f'工程含链接：{rel}')
        if p.is_file():
            safe_file(directory, rel)
            sha, size = hash_file(p)
            files[rel] = {'sha256': sha, 'size': size}
    return files


def seal_project(directory):
    """Commit a producer's output manifest, without copying any asset bytes."""
    data = read_project(directory)
    if not data:
        raise ValueError('不是规范工程')
    for field in ('cover_custom', 'banner_custom', 'icon_custom'):
        raw = data['metadata'].get(field)
        if raw:
            source = Path(raw)
            if source.is_absolute():
                if not source.resolve().is_relative_to(Path(directory).resolve()):
                    raise ValueError('自定义素材必须先导入工程内')
    files = file_manifest(directory)
    source_dirs=sorted(p.name for p in Path(directory).iterdir() if p.is_dir()
                       and (p.name in SOURCE_DIRS or p.name.startswith('原图_')))
    return update_project(directory, lambda d: d.update(files=files,source_directories=source_dirs), data['revision_id'])


def create_project(directory, metadata, mode='full', meanings=None, characters=None):
    directory = Path(directory)
    if not metadata.get('work_id'):
        metadata = dict(metadata, work_id=uuid.uuid4().hex)
    if (directory / 'project.json').exists():
        raise ValueError('工程已存在，不能覆盖')
    data = dict(format=FORMAT, schema_version=SCHEMA, mode=mode,
                metadata=metadata, meaning_map=meanings or {}, characters=characters or [],
                source_directories=sorted(p.name for p in directory.iterdir()
                    if p.is_dir() and (p.name in SOURCE_DIRS or p.name.startswith('原图_'))),
                revision_id=uuid.uuid4().hex, files={})
    atomic_json(directory / 'project.json', data)
    return seal_project(directory)


def rename_project(directory, name):
    directory = Path(directory)
    data = read_project(directory)
    if not data:
        return directory
    destination = named_destination(directory.parent, name, data['metadata']['work_id'])
    if destination != directory:
        if destination.exists():
            raise ValueError('同一作品存在两个工程目录，请先处理')
        with project_lock(directory):
            # Windows cannot rename a directory while its lock file is open.
            pass
        directory.rename(destination)
    return destination
