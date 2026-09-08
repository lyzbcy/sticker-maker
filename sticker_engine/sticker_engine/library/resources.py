"""Portable path and content-addressed resource helpers.

The catalog owns revision and graph semantics.  This module keeps the small,
platform-neutral rules that are shared by object ingestion and materializing a
revision into a working directory.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Tuple


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Status/refresh calls construct short-lived ResourceLibrary instances, while
# the same content-addressed objects may be checked on every call.  Keep a
# small process-level cache keyed by the full stat identity so those reads do
# not rehash gigabytes of unchanged data.  A bounded cache prevents a large
# library or a long running desktop process from retaining every path ever
# seen.  Entries are added only after a matching post-read stat check.
_HASH_CACHE: "OrderedDict[Tuple[str, int, int, int, int, int], Tuple[str, int]]" = OrderedDict()
_HASH_CACHE_LIMIT = 4096
_HASH_CACHE_LOCK = threading.RLock()


def validate_identifier(value: object, field: str = "identifier") -> str:
    """Validate a portable account/work/revision identifier."""

    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"invalid {field}")
    if value in {".", ".."}:
        raise ValueError(f"invalid {field}")
    if value[-1] in ". ":
        raise ValueError(f"invalid {field}")
    if value.upper().split(".", 1)[0] in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"invalid {field}")
    return value


def validate_hash(value: object, field: str = "sha256") -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _validate_component(component: str) -> str:
    if not component or component in {".", ".."}:
        raise ValueError("path traversal is not allowed")
    if component[-1] in ". ":
        raise ValueError("portable paths cannot end with a dot or space")
    if component.upper().split(".", 1)[0] in WINDOWS_RESERVED_NAMES:
        raise ValueError("reserved Windows name")
    if any(ord(char) < 32 or ord(char) == 127 for char in component):
        raise ValueError("control character in path")
    if ":" in component:
        raise ValueError("colon is not portable")
    if len(component) > 255:
        raise ValueError("path component is too long")
    return unicodedata.normalize("NFC", component)


def validate_logical_path(value: object) -> str:
    """Return a canonical POSIX-style logical path or raise ``ValueError``.

    Logical paths are deliberately stricter than POSIX permits so that the
    same manifest can be materialized on Windows and macOS without escaping a
    target directory or colliding only by case.
    """

    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("logical path must be a non-empty string")
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("logical path must be relative POSIX text")
    components = value.split("/")
    normalized = "/".join(_validate_component(component) for component in components)
    if normalized != value:
        # Normalization is safe for a caller that explicitly asks for it, but
        # manifests must be canonical and deterministic.
        raise ValueError("logical path is not canonical")
    return normalized


def validate_episode_metadata_paths(metadata: dict) -> dict:
    """Validate path-valued fields carried by an episode manifest.

    Shared metadata must be portable across Windows and macOS.  Empty values
    mean the matching asset mode does not use a custom file.
    """

    for field in ("cover_custom", "banner_custom", "icon_custom"):
        if field not in metadata or metadata[field] == "":
            continue
        value = metadata[field]
        if not isinstance(value, str):
            raise ValueError(f"metadata.{field} must be a portable relative path")
        try:
            validate_logical_path(value)
        except ValueError as exc:
            raise ValueError(f"metadata.{field}: {exc}") from exc
    return metadata


def validate_settings_metadata_paths(metadata: dict) -> dict:
    """Validate logical paths embedded in shared settings metadata.

    Settings are applied on another machine, so a path in a series or prefs
    payload must remain inside the catalog's portable namespace.  The runtime
    may map these logical names to an absolute local workspace only after the
    manifest has passed this check.
    """

    if metadata.get("kind") != "settings":
        return metadata

    logical_path = metadata.get("logical_path")
    if logical_path not in (None, ""):
        try:
            validate_logical_path(logical_path)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata.logical_path: {exc}") from exc

    setting_type = metadata.get("setting_type")
    payload = metadata.get("payload")
    if payload is None:
        return metadata
    if not isinstance(payload, dict):
        raise ValueError("metadata.payload must be an object")

    if setting_type == "prefs" and payload.get("reference_lib_path") not in (None, ""):
        reference_path = payload["reference_lib_path"]
        try:
            normalized = validate_logical_path(reference_path)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata.payload.reference_lib_path: {exc}") from exc
        if normalized != "reference_library" and not normalized.startswith("reference_library/"):
            raise ValueError(
                "metadata.payload.reference_lib_path must be inside reference_library"
            )

    if setting_type == "series":
        role_map = payload.get("role_asset_map")
        if role_map is not None and not isinstance(role_map, dict):
            raise ValueError("metadata.payload.role_asset_map must be an object")
        for role_assets in (role_map or {}).values():
            if not isinstance(role_assets, dict):
                continue
            for value in role_assets.values():
                if value in (None, ""):
                    continue
                if not isinstance(value, str):
                    raise ValueError("metadata.payload.role_asset_map paths must be strings")
                try:
                    validate_logical_path(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"metadata.payload.role_asset_map path: {exc}"
                    ) from exc

    return metadata


def validate_case_unique(paths: Iterable[str]) -> None:
    seen = {}
    for path in paths:
        folded = unicodedata.normalize("NFC", path).casefold()
        previous = seen.get(folded)
        if previous is not None and previous != path:
            raise ValueError(f"case-colliding logical paths: {previous!r}, {path!r}")
        seen[folded] = path


def hash_file(path: Path) -> Tuple[str, int]:
    """Hash a regular file without following a symbolic link."""

    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"resource is not a regular file: {path}")
    try:
        before = path.stat()
    except OSError as exc:
        raise ValueError(f"resource is not readable: {path}") from exc
    resolved = str(path.resolve(strict=False))
    cache_key = (
        resolved,
        int(getattr(before, "st_dev", 0)),
        int(getattr(before, "st_ino", 0)),
        int(before.st_size),
        int(getattr(before, "st_mtime_ns", int(before.st_mtime * 1_000_000_000))),
        int(getattr(before, "st_ctime_ns", int(before.st_ctime * 1_000_000_000))),
    )
    with _HASH_CACHE_LOCK:
        cached = _HASH_CACHE.get(cache_key)
        if cached is not None:
            _HASH_CACHE.move_to_end(cache_key)
            return cached
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        after = path.stat()
    except OSError as exc:
        raise ValueError(f"resource could not be read: {path}") from exc
    after_key = (
        resolved,
        int(getattr(after, "st_dev", 0)),
        int(getattr(after, "st_ino", 0)),
        int(after.st_size),
        int(getattr(after, "st_mtime_ns", int(after.st_mtime * 1_000_000_000))),
        int(getattr(after, "st_ctime_ns", int(after.st_ctime * 1_000_000_000))),
    )
    if after_key != cache_key:
        raise ValueError(f"resource changed while being read: {path}")
    result = (digest.hexdigest(), size)
    with _HASH_CACHE_LOCK:
        _HASH_CACHE[cache_key] = result
        _HASH_CACHE.move_to_end(cache_key)
        while len(_HASH_CACHE) > _HASH_CACHE_LIMIT:
            _HASH_CACHE.popitem(last=False)
    return result


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes beside ``path`` and atomically publish them."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def is_sync_conflict_name(name: str) -> bool:
    return "sync-conflict" in name.lower()


def is_sync_temporary_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in {".stfolder", ".stignore"}
        or lowered.startswith("~syncthing~")
        or lowered.startswith(".~syncthing~")
        or lowered.endswith((".tmp", ".part", ".swp"))
    )
