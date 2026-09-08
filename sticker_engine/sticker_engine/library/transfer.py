"""Durable export and migration transactions for account resource libraries.

The transfer layer deliberately owns the transaction, rather than accepting a
second list of files from the caller during execution.  A preview records the
source roots, file snapshots, and cleanup scope.  Execution can therefore be
resumed after cancellation or a process crash without allowing a stale UI to
replace the deletion scope.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .deletion import safe_unlink_verified
from .resources import is_sync_conflict_name, is_sync_temporary_name


_PLAN_VERSION = 1
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class TransferError(RuntimeError):
    """Raised for invalid transfer requests before a plan is created."""


class _SnapshotError(RuntimeError):
    """A file could not be read consistently enough to snapshot."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_path(value: Any, *, name: str) -> Path:
    if isinstance(value, Path):
        return value.expanduser()
    if isinstance(value, str):
        if not value:
            raise ValueError(f"{name} must not be empty")
        return Path(value).expanduser()
    raise TypeError(f"{name} must be a path or string")


def _canonical(path: Path) -> Path:
    # strict=False is important for a new destination and for a source that is
    # currently offline.  resolve() still normalises existing symlink parents.
    return path.resolve(strict=False)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _same_or_nested(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"value is not JSON serialisable: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(records: Iterable[Any]) -> str:
    return _digest_bytes(_canonical_json(list(records)).encode("utf-8"))


def _safe_logical_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("logical path must be a non-empty string")
    # A backslash is a separator on Windows and a valid POSIX filename on
    # macOS.  Rejecting it makes a manifest portable in both directions.
    if "\\" in value or value.startswith("/") or _DRIVE_PATH.match(value):
        raise ValueError(f"unsafe logical path: {value!r}")
    path = PurePosixPath(value)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe logical path: {value!r}")
    for part in parts:
        if part.casefold().split(".", 1)[0] in _WINDOWS_RESERVED:
            raise ValueError(f"unsafe logical path: {value!r}")
    return "/".join(parts)


def _sensitive_component(component: str) -> bool:
    lower = component.casefold()
    if lower in {
        ".env",
        "auth.json",
        "credentials.json",
        "cookies",
        "cookie",
        "login data",
        "web data",
        ".stfolder",
        ".stignore",
        ".stversions",
        ".syncthing",
        ".ds_store",
    }:
        return True
    if lower.startswith(".env.") or lower.startswith(".st") or lower.startswith(".syncthing"):
        return True
    if "cookie" in lower or "sync-conflict" in lower:
        return True
    if lower in {
        "browser",
        "browser-state",
        "browser_data",
        "browser-data",
        "chromium",
        "chrome",
        "firefox",
        "playwright",
        "local storage",
        "session storage",
        "sessions",
        "login data",
        "history",
    }:
        return True
    return False


def _is_sensitive(relative: str) -> bool:
    return any(_sensitive_component(part) for part in PurePosixPath(relative).parts)


def _is_root_meta(relative: str) -> bool:
    return relative == "meta.json"


def _stat_fingerprint(st: os.stat_result) -> Dict[str, int]:
    return {
        "size": int(st.st_size),
        "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
        "inode": int(getattr(st, "st_ino", 0)),
        "device": int(getattr(st, "st_dev", 0)),
    }


def _snapshot_file(path: Path) -> Dict[str, Any]:
    """Return a content and identity snapshot, detecting a read-time race."""

    try:
        first = path.stat()
        if not stat.S_ISREG(first.st_mode):
            raise _SnapshotError("not a regular file")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        second = path.stat()
    except (OSError, ValueError) as exc:
        raise _SnapshotError(str(exc)) from exc
    before = _stat_fingerprint(first)
    after = _stat_fingerprint(second)
    if before != after:
        raise _SnapshotError("source changed while it was being read")
    return {
        "sha256": digest.hexdigest(),
        "size": before["size"],
        "mtime_ns": before["mtime_ns"],
        "inode": before["inode"],
        "device": before["device"],
    }


def _snapshot_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    # Hash/size are the content guarantee.  mtime and inode additionally catch
    # a replaced file whose bytes happen to be the same, which matters before
    # deleting a user's source.
    return all(
        expected.get(key) == actual.get(key)
        for key in ("sha256", "size", "mtime_ns", "inode", "device")
    )


def _call_stop(callback: Optional[Callable[..., Any]]) -> bool:
    if callback is None:
        return False
    try:
        return bool(callback())
    except TypeError:
        return bool(callback(None))


def _call_progress(callback: Optional[Callable[..., Any]], event: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(dict(event))
    except TypeError:
        # A small compatibility concession for callers that used the older
        # ``progress(done, total)`` callback shape.
        callback(event.get("completed", 0), event.get("total", 0))


class TransferManager:
    """Create, persist, and execute safe resource-library transfer plans."""

    def __init__(self, state_dir: Any):
        self.state_dir = _canonical(_as_path(state_dir, name="state_dir"))
        self.plan_dir = self.state_dir / "plans"
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        self.task_index = self.state_dir / "tasks.json"

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------
    def preview(
        self,
        sources: Sequence[Mapping[str, Any]],
        target: Any,
        mode: str = "backup",
        cleanup: bool = False,
        library_roots: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        if mode not in {"backup", "migration"}:
            raise ValueError("mode must be 'backup' or 'migration'")
        if cleanup and mode != "migration":
            raise ValueError("cleanup is only available for migration plans")
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
            raise TypeError("sources must be a sequence of source records")

        # A whole catalog is a different transfer unit from an episode
        # directory.  Keep the explicit API below as the durable path, while
        # accepting ``preview([], ..., library_roots=[...])`` for callers that
        # already construct preview arguments from the command boundary.
        if library_roots:
            if sources:
                raise ValueError("library_roots cannot be combined with episode sources")
            return self.preview_library(library_roots, target, mode=mode, cleanup=cleanup)

        target_path = _canonical(_as_path(target, name="target"))
        source_records: List[Dict[str, Any]] = []
        roots: List[Path] = []
        for index, raw in enumerate(sources):
            if not isinstance(raw, Mapping):
                raise TypeError(f"source {index} must be a mapping")
            if "path" not in raw:
                raise ValueError(f"source {index} is missing path")
            root_input = _as_path(raw["path"], name=f"sources[{index}].path")
            if root_input.is_symlink():
                raise ValueError(f"source {root_input} must not be a symlink")
            root = _canonical(root_input)
            if _same_or_nested(root, target_path):
                raise ValueError("source and target must not be equal or nested")
            roots.append(root)
            source_records.append(
                {
                    "source_id": uuid.uuid4().hex,
                    "path": str(root),
                    "source_root": str(root),
                    "account_id": str(raw.get("account_id", "")),
                    "work_id": str(raw.get("work_id", "")),
                    "metadata": _json_safe(raw.get("metadata") or {}),
                    "extra_files": _json_safe(dict(raw.get("extra_files") or {})),
                    "library_root": None,
                    "library_revision_id": None,
                    "entry_ids": [],
                    "managed_paths": [],
                    "snapshot_paths": [],
                    "missing": [],
                    "revision_id": None,
                    "revision_fingerprint": None,
                    "state": "planned",
                }
            )
            if not source_records[-1]["account_id"] or not source_records[-1]["work_id"]:
                raise ValueError("each source requires account_id and work_id")
            library_root_value = raw.get("library_root")
            revision_value = raw.get("revision_id")
            if library_root_value is not None or revision_value is not None:
                if library_root_value is None or revision_value is None:
                    raise ValueError("library_root and revision_id must be supplied together")
                library_root_input = _as_path(library_root_value, name="library_root")
                if library_root_input.is_symlink():
                    raise ValueError(f"library_root {library_root_input} must not be a symlink")
                library_root = _canonical(library_root_input)
                if _same_or_nested(library_root, target_path):
                    raise ValueError("library_root and target must not be equal or nested")
                source_records[-1]["library_root"] = str(library_root)
                source_records[-1]["library_revision_id"] = str(revision_value)

        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if _same_or_nested(left, right):
                    raise ValueError("source directories must not overlap")

        entries: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        for source in source_records:
            root = Path(source["path"])
            scanned, scan_missing = self._scan_root(source, root)
            for item in scanned:
                self._add_entry(entries, source, item)
            for item in scan_missing:
                self._add_missing(missing, source, item)

            extras = source["extra_files"]
            if not isinstance(extras, Mapping):
                raise TypeError("extra_files must be a mapping")
            existing_logical = {item["logical_path"] for item in scanned}
            for logical_raw, source_raw in sorted(extras.items(), key=lambda pair: str(pair[0])):
                try:
                    logical = _safe_logical_path(str(logical_raw))
                except (TypeError, ValueError) as exc:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": str(logical_raw),
                            "source_path": str(source_raw),
                            "reason": f"unsafe_logical_path: {exc}",
                            "external": True,
                            "managed": False,
                        },
                    )
                    continue
                if logical in existing_logical:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(source_raw),
                            "reason": "duplicate_logical_path",
                            "external": True,
                            "managed": False,
                        },
                    )
                    continue
                extra_item = self._scan_extra(source, root, logical, source_raw, target_path)
                if extra_item.get("missing"):
                    self._add_missing(missing, source, extra_item)
                else:
                    self._add_entry(entries, source, extra_item)

            source["snapshot_paths"] = sorted(set(source["managed_paths"]))
            source["snapshot_fingerprint"] = self._source_fingerprint(source, entries)

        entries.sort(key=lambda item: (item["source_id"], item["logical_path"], item["entry_id"]))
        missing.sort(key=lambda item: (item["source_id"], item.get("logical_path", ""), item.get("reason", "")))
        bytes_total = sum(int(item.get("size", 0)) for item in entries if item.get("capture", True))
        plan_id = uuid.uuid4().hex
        plan = {
            "plan_version": _PLAN_VERSION,
            "plan_id": plan_id,
            "created_at": _now(),
            "updated_at": _now(),
            "mode": mode,
            "target": str(target_path),
            "cleanup": bool(cleanup),
            "state": "planned",
            "sources": source_records,
            "entries": entries,
            "work_entries": [
                {
                    "source_id": source["source_id"],
                    "account_id": source["account_id"],
                    "work_id": source["work_id"],
                    "metadata": source["metadata"],
                    "source_root": source["source_root"],
                    "entry_ids": list(source.get("entry_ids") or []),
                    "missing_ids": list(source.get("missing") or []),
                    "bytes": sum(
                        int(entry.get("size", 0))
                        for entry in entries
                        if entry.get("source_id") == source["source_id"] and entry.get("capture", True)
                    ),
                }
                for source in source_records
            ],
            "missing": missing,
            "bytes": bytes_total,
            "byte_count": bytes_total,
            "bytes_total": bytes_total,
            "bytes_available": bytes_total,
            "bytes_missing": sum(int(item.get("size", 0)) for item in missing),
            "snapshot_fingerprint": _fingerprint(
                {
                    "library_roots": [],
                    "sources": [
                    {
                        "account_id": source["account_id"],
                        "work_id": source["work_id"],
                        "fingerprint": source.get("snapshot_fingerprint"),
                    }
                    for source in source_records
                    ],
                }
            ),
            "activation_attempted": False,
            "activated": False,
            "conflicts": [],
            "errors": [],
            "cleanup_errors": [],
            "library_roots": [],
            "library_merges": [],
        }
        self._save_plan(plan)
        return plan

    def preview_library(
        self,
        library_roots: Optional[Sequence[Any]] = None,
        target: Any = None,
        mode: str = "backup",
        cleanup: bool = False,
        *,
        library_root: Any = None,
    ) -> Dict[str, Any]:
        """Create a plan for copying one or more complete resource libraries.

        Episode previews only see materialized working directories.  A library
        preview instead inventories the immutable root itself, so an account
        with no local episodes still transfers settings, operation records,
        deleted work history, manifests, and orphaned content-addressed
        objects.  Validation is deliberately performed during preview; an
        incomplete source is retained in the plan and can never activate a
        migration later.
        """

        if mode not in {"backup", "migration"}:
            raise ValueError("mode must be 'backup' or 'migration'")
        if cleanup and mode != "migration":
            raise ValueError("cleanup is only available for migration plans")
        if library_root is not None:
            if library_roots:
                raise ValueError("library_root and library_roots cannot both be supplied")
            library_roots = [library_root]
        if isinstance(library_roots, (str, bytes)):
            library_roots = [library_roots]
        if not isinstance(library_roots, Sequence) or not library_roots:
            raise ValueError("library_roots must contain at least one root")

        target_path = _canonical(_as_path(target, name="target"))
        roots: List[Path] = []
        for index, raw_root in enumerate(library_roots):
            root_input = _as_path(raw_root, name=f"library_roots[{index}]")
            if root_input.is_symlink():
                raise ValueError(f"library root {root_input} must not be a symlink")
            root = _canonical(root_input)
            if _same_or_nested(root, target_path):
                raise ValueError("library root and target must not be equal or nested")
            if root not in roots:
                roots.append(root)
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if _same_or_nested(left, right):
                    raise ValueError("library roots must not overlap")

        entries: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        library_sources: List[Dict[str, Any]] = []
        for root in roots:
            source = {
                "source_id": uuid.uuid4().hex,
                "path": str(root),
                "source_root": str(root),
                "library_root": str(root),
                "library_id": None,
                "account_id": "",
                "work_id": "",
                "metadata": {},
                "entry_ids": [],
                "managed_paths": [],
                "snapshot_paths": [],
                "missing": [],
                "state": "planned",
            }
            library_sources.append(source)
            if not root.exists():
                self._add_missing(
                    missing,
                    source,
                    {
                        "logical_path": "",
                        "source_path": str(root),
                        "reason": "library_missing",
                        "external": False,
                        "managed": True,
                    },
                )
                source["state"] = "incomplete"
                continue
            if not root.is_dir():
                self._add_missing(
                    missing,
                    source,
                    {
                        "logical_path": "",
                        "source_path": str(root),
                        "reason": "library_not_directory",
                        "external": False,
                        "managed": True,
                    },
                )
                source["state"] = "incomplete"
                continue
            self._scan_library_root(source, root, entries, missing)
            source["snapshot_paths"] = sorted(set(source["managed_paths"]))
            source["snapshot_fingerprint"] = self._source_fingerprint(source, entries)
            source["state"] = "incomplete" if source.get("missing") else "ready"

        entries.sort(key=lambda item: (item["source_id"], item["logical_path"], item["entry_id"]))
        missing.sort(
            key=lambda item: (
                item.get("source_id", ""),
                item.get("logical_path", ""),
                item.get("reason", ""),
            )
        )
        bytes_total = sum(int(item.get("size", 0)) for item in entries)
        object_count = sum(1 for item in entries if item.get("library_kind") == "object")
        manifest_count = sum(1 for item in entries if item.get("library_kind") == "manifest")
        plan_id = uuid.uuid4().hex
        plan = {
            "plan_version": _PLAN_VERSION,
            "plan_id": plan_id,
            "created_at": _now(),
            "updated_at": _now(),
            "mode": mode,
            "target": str(target_path),
            "cleanup": bool(cleanup),
            "state": "planned",
            "full_library": True,
            "library_copy": True,
            "sources": [],
            "library_roots": [str(root) for root in roots],
            "library_sources": library_sources,
            "entries": entries,
            "library_entries": entries,
            "work_entries": [],
            "missing": missing,
            "bytes": bytes_total,
            "byte_count": bytes_total,
            "bytes_total": bytes_total,
            "bytes_available": bytes_total,
            "bytes_missing": sum(int(item.get("size", 0)) for item in missing),
            "object_count": object_count,
            "manifest_count": manifest_count,
            "snapshot_fingerprint": _fingerprint(
                [
                    {
                        "library_root": source["library_root"],
                        "library_id": source.get("library_id"),
                        "fingerprint": source.get("snapshot_fingerprint"),
                    }
                    for source in library_sources
                ]
            ),
            "activation_attempted": False,
            "activated": False,
            "conflicts": [],
            "errors": [],
            "cleanup_errors": [],
            "library_merges": [],
        }
        self._save_plan(plan)
        return plan

    @staticmethod
    def _library_private_component(name: str) -> bool:
        lower = name.casefold()
        if lower in {
            ".env",
            ".stfolder",
            ".stignore",
            ".stversions",
            "auth.json",
            "credentials.json",
            "cookies",
            "cookie",
            "browser",
            "browser-state",
            "browser_data",
            "browser-data",
            "local storage",
            "session storage",
            "device.json",
        }:
            return True
        return lower.startswith(".env.") or "cookie" in lower

    def _scan_library_root(
        self,
        source: Dict[str, Any],
        root: Path,
        entries: List[Dict[str, Any]],
        missing: List[Dict[str, Any]],
    ) -> None:
        """Scan and validate a library root without changing it."""

        try:
            from .catalog import ResourceLibrary

            source_library = ResourceLibrary(root, create=False)
            source["library_id"] = source_library.library_id
        except Exception as exc:
            self._add_missing(
                missing,
                source,
                {
                    "logical_path": "library.json",
                    "source_path": str(root / "library.json"),
                    "reason": f"library_invalid: {exc}",
                    "external": False,
                    "managed": True,
                },
            )
            source_library = None

        def walk(directory: Path, prefix: str) -> None:
            try:
                children = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
            except OSError as exc:
                self._add_missing(
                    missing,
                    source,
                    {
                        "logical_path": prefix,
                        "source_path": str(directory),
                        "reason": f"scan_failed: {exc}",
                        "external": False,
                        "managed": True,
                    },
                )
                return
            for child in children:
                relative = f"{prefix}/{child.name}" if prefix else child.name
                if any(
                    self._library_private_component(part)
                    for part in PurePosixPath(relative).parts
                ):
                    continue
                child_path = Path(child.path)
                try:
                    logical = _safe_logical_path(relative)
                except ValueError as exc:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": relative,
                            "source_path": str(child_path),
                            "reason": f"unsafe_logical_path: {exc}",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                if is_sync_conflict_name(child.name):
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": "sync_conflict_file",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                if is_sync_temporary_name(child.name):
                    continue
                if child.is_symlink():
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": "symlink_not_followed",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                try:
                    is_dir = child.is_dir(follow_symlinks=False)
                    is_file = child.is_file(follow_symlinks=False)
                except OSError as exc:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": f"stat_failed: {exc}",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                if is_dir:
                    walk(child_path, logical)
                    continue
                if not is_file:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": "unsupported_file_type",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                try:
                    snapshot = _snapshot_file(child_path)
                except _SnapshotError as exc:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": f"snapshot_failed: {exc}",
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                library_kind = (
                    "library_metadata"
                    if logical == "library.json"
                    else "object"
                    if logical.startswith("objects/")
                    else "manifest"
                    if re.fullmatch(r"accounts/[^/]+/works/[^/]+/revisions/[^/]+\.json", logical)
                    else "library_file"
                )
                self._add_entry(
                    entries,
                    source,
                    {
                        "logical_path": logical,
                        "source_path": str(child_path),
                        "source_relative": logical,
                        "external": False,
                        "managed": library_kind != "library_file",
                        "capture": True,
                        "cleanup_only": False,
                        "library_kind": library_kind,
                        **snapshot,
                    },
                )
                if library_kind == "object":
                    expected = PurePosixPath(logical).name
                    if not re.fullmatch(r"[0-9a-f]{64}", expected) or snapshot["sha256"] != expected:
                        self._add_missing(
                            missing,
                            source,
                            {
                                "logical_path": logical,
                                "source_path": str(child_path),
                                "reason": "corrupt_object",
                                "expected_sha256": expected,
                                "actual_sha256": snapshot["sha256"],
                                "size": snapshot["size"],
                                "external": False,
                                "managed": True,
                            },
                        )

        walk(root, "")
        if source_library is None:
            return
        self._validate_library_references(source_library, source, root, missing)

    def _validate_library_references(
        self,
        source_library: Any,
        source: Dict[str, Any],
        root: Path,
        missing: List[Dict[str, Any]],
    ) -> None:
        """Validate every manifest/object relationship in a source catalog."""

        try:
            manifest_paths = list(source_library._iter_manifest_paths([]))
        except Exception as exc:
            self._add_missing(
                missing,
                source,
                {
                    "logical_path": "accounts",
                    "source_path": str(root / "accounts"),
                    "reason": f"manifest_scan_failed: {exc}",
                    "external": False,
                    "managed": True,
                },
            )
            return

        parsed: Dict[Tuple[str, str], Dict[str, Mapping[str, Any]]] = {}
        for path, account_id, work_id, revision_id in manifest_paths:
            try:
                revision = source_library._load_revision(path, account_id, work_id, revision_id)
            except Exception as exc:
                self._add_missing(
                    missing,
                    source,
                    {
                        "logical_path": str(path.relative_to(root)),
                        "source_path": str(path),
                        "reason": f"manifest_invalid: {exc}",
                        "external": False,
                        "managed": True,
                    },
                )
                continue
            parsed.setdefault((account_id, work_id), {})[revision_id] = revision
            for resource in (revision.get("files") or {}).values():
                digest = resource["sha256"]
                object_path = root / "objects" / digest[:2] / digest
                if not object_path.exists():
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": str(object_path.relative_to(root)).replace(os.sep, "/"),
                            "source_path": str(object_path),
                            "reason": "referenced_object_missing",
                            "expected_sha256": digest,
                            "size": int(resource["size"]),
                            "external": False,
                            "managed": True,
                        },
                    )
                    continue
                try:
                    actual = _snapshot_file(object_path)
                except _SnapshotError as exc:
                    self._add_missing(
                        missing,
                        source,
                        {
                            "logical_path": str(object_path.relative_to(root)).replace(os.sep, "/"),
                            "source_path": str(object_path),
                            "reason": f"referenced_object_unreadable: {exc}",
                            "expected_sha256": digest,
                            "size": int(resource["size"]),
                            "external": False,
                            "managed": True,
                        },
                    )
                else:
                    if actual["sha256"] != digest or int(actual["size"]) != int(resource["size"]):
                        self._add_missing(
                            missing,
                            source,
                            {
                                "logical_path": str(object_path.relative_to(root)).replace(os.sep, "/"),
                                "source_path": str(object_path),
                                "reason": "referenced_object_corrupt",
                                "expected_sha256": digest,
                                "actual_sha256": actual["sha256"],
                                "expected_size": int(resource["size"]),
                                "actual_size": int(actual["size"]),
                                "external": False,
                                "managed": True,
                            },
                        )

        for (account_id, work_id), revisions in parsed.items():
            for revision in revisions.values():
                for parent_id in revision.get("parents") or []:
                    if parent_id not in revisions:
                        self._add_missing(
                            missing,
                            source,
                            {
                                "logical_path": str(
                                    root
                                    / "accounts"
                                    / account_id
                                    / "works"
                                    / work_id
                                    / "revisions"
                                    / f"{parent_id}.json"
                                ).replace(str(root) + os.sep, "").replace(os.sep, "/"),
                                "source_path": str(
                                    root
                                    / "accounts"
                                    / account_id
                                    / "works"
                                    / work_id
                                    / "revisions"
                                    / f"{parent_id}.json"
                                ),
                                "reason": "parent_revision_missing",
                                "external": False,
                                "managed": True,
                            },
                        )

        # This catches graph loops and other catalog-level validation errors
        # while still allowing the scan above to report every missing object.
        try:
            source_library.list_works()
        except Exception as exc:
            self._add_missing(
                missing,
                source,
                {
                    "logical_path": "accounts",
                    "source_path": str(root / "accounts"),
                    "reason": f"library_validation_failed: {exc}",
                    "external": False,
                    "managed": True,
                },
            )

    def _scan_root(
        self, source: Mapping[str, Any], root: Path
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        entries: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        if root.is_symlink():
            raise ValueError(f"source {root} must not be a symlink")
        if not root.exists():
            missing.append(
                {
                    "logical_path": "",
                    "source_path": str(root),
                    "reason": "source_missing",
                    "external": False,
                    "managed": True,
                }
            )
            return entries, missing
        if not root.is_dir():
            missing.append(
                {
                    "logical_path": "",
                    "source_path": str(root),
                    "reason": "source_not_directory",
                    "external": False,
                    "managed": True,
                }
            )
            return entries, missing

        def walk(directory: Path, relative_prefix: str) -> None:
            try:
                children = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
            except OSError as exc:
                missing.append(
                    {
                        "logical_path": relative_prefix,
                        "source_path": str(directory),
                        "reason": f"scan_failed: {exc}",
                        "external": False,
                        "managed": True,
                    }
                )
                return
            for child in children:
                relative = f"{relative_prefix}/{child.name}" if relative_prefix else child.name
                try:
                    logical = _safe_logical_path(relative)
                except ValueError as exc:
                    missing.append(
                        {
                            "logical_path": relative,
                            "source_path": str(Path(child.path)),
                            "reason": f"unsafe_logical_path: {exc}",
                            "external": False,
                            "managed": True,
                        }
                    )
                    continue
                if _is_sensitive(logical):
                    continue
                child_path = Path(child.path)
                if child.is_symlink():
                    missing.append(
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": "symlink_not_followed",
                            "external": False,
                            "managed": True,
                        }
                    )
                    continue
                try:
                    is_dir = child.is_dir(follow_symlinks=False)
                    is_file = child.is_file(follow_symlinks=False)
                except OSError as exc:
                    missing.append(
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": f"stat_failed: {exc}",
                            "external": False,
                            "managed": True,
                        }
                    )
                    continue
                if is_dir:
                    walk(child_path, logical)
                    continue
                if not is_file:
                    missing.append(
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": "unsupported_file_type",
                            "external": False,
                            "managed": True,
                        }
                    )
                    continue
                try:
                    snapshot = _snapshot_file(child_path)
                except _SnapshotError as exc:
                    missing.append(
                        {
                            "logical_path": logical,
                            "source_path": str(child_path),
                            "reason": f"snapshot_failed: {exc}",
                            "external": False,
                            "managed": True,
                        }
                    )
                    continue
                item = {
                    "logical_path": logical,
                    "source_path": str(child_path),
                    "source_relative": logical,
                    "external": False,
                    "managed": True,
                    "capture": not _is_root_meta(logical),
                    "cleanup_only": _is_root_meta(logical),
                    **snapshot,
                }
                entries.append(item)

        walk(root, "")
        return entries, missing

    def _scan_extra(
        self,
        source: Mapping[str, Any],
        root: Path,
        logical: str,
        source_value: Any,
        target: Optional[Path] = None,
    ) -> Dict[str, Any]:
        try:
            raw_path = _as_path(source_value, name="extra file")
        except (TypeError, ValueError) as exc:
            return {
                "logical_path": logical,
                "source_path": str(source_value),
                "reason": f"invalid_extra_path: {exc}",
                "external": True,
                "managed": False,
                "missing": True,
            }
        if not raw_path.is_absolute():
            return {
                "logical_path": logical,
                "source_path": str(raw_path),
                "reason": "extra_path_must_be_absolute",
                "external": True,
                "managed": False,
                "missing": True,
            }
        candidate = _canonical(raw_path)
        if target is not None and _same_or_nested(candidate, target):
            raise ValueError("external dependency and target must not be equal or nested")
        if _is_sensitive(logical) or _is_sensitive(raw_path.name):
            return {
                "logical_path": logical,
                "source_path": str(raw_path),
                "reason": "excluded_sensitive_file",
                "external": True,
                "managed": False,
                "missing": True,
            }
        if raw_path.is_symlink():
            return {
                "logical_path": logical,
                "source_path": str(raw_path),
                "reason": "symlink_not_followed",
                "external": not _is_within(_canonical(raw_path), root),
                "managed": False,
                "missing": True,
            }
        source_path = candidate
        managed = _is_within(source_path, root) and source_path != root
        if not source_path.exists():
            return {
                "logical_path": logical,
                "source_path": str(source_path),
                "source_relative": str(source_path.relative_to(root)).replace(os.sep, "/")
                if managed
                else None,
                "reason": "dependency_missing",
                "external": not managed,
                "managed": managed,
                "missing": True,
            }
        try:
            snapshot = _snapshot_file(source_path)
        except _SnapshotError as exc:
            return {
                "logical_path": logical,
                "source_path": str(source_path),
                "source_relative": str(source_path.relative_to(root)).replace(os.sep, "/")
                if managed
                else None,
                "reason": f"snapshot_failed: {exc}",
                "external": not managed,
                "managed": managed,
                "missing": True,
            }
        return {
            "logical_path": logical,
            "source_path": str(source_path),
            "source_relative": str(source_path.relative_to(root)).replace(os.sep, "/")
            if managed
            else None,
            "external": not managed,
            "managed": managed,
            "capture": True,
            "cleanup_only": False,
            **snapshot,
        }

    @staticmethod
    def _add_entry(entries: List[Dict[str, Any]], source: Dict[str, Any], item: Dict[str, Any]) -> None:
        entry = {
            "entry_id": uuid.uuid4().hex,
            "source_id": source["source_id"],
            "account_id": source["account_id"],
            "work_id": source["work_id"],
            "metadata": source["metadata"],
            "source_root": source["source_root"],
            "status": "planned",
            "error": None,
            **{key: value for key, value in item.items() if key != "missing"},
        }
        entry.setdefault("path", entry.get("source_path"))
        entry.setdefault("destination", entry.get("logical_path"))
        entry.setdefault("target", entry.get("logical_path"))
        entry.setdefault("capture", True)
        entry.setdefault("cleanup_only", False)
        source["entry_ids"].append(entry["entry_id"])
        if entry.get("managed") and entry.get("source_relative"):
            source["managed_paths"].append(entry["source_relative"])
        entries.append(entry)

    @staticmethod
    def _add_missing(missing: List[Dict[str, Any]], source: Dict[str, Any], item: Dict[str, Any]) -> None:
        record = {
            "missing_id": uuid.uuid4().hex,
            "source_id": source["source_id"],
            "account_id": source["account_id"],
            "work_id": source["work_id"],
            **{key: value for key, value in item.items() if key != "missing"},
        }
        record.setdefault("path", record.get("source_path"))
        record.setdefault("destination", record.get("logical_path"))
        record.setdefault("target", record.get("logical_path"))
        missing.append(record)
        source["missing"].append(record["missing_id"])
        if record.get("managed") and record.get("source_relative"):
            source["managed_paths"].append(record["source_relative"])

    @staticmethod
    def _source_fingerprint(source: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> str:
        records = [
            {
                "logical_path": item["logical_path"],
                "source_relative": item.get("source_relative"),
                "sha256": item.get("sha256"),
                "size": item.get("size"),
                "capture": item.get("capture", True),
            }
            for item in entries
            if item.get("source_id") == source.get("source_id")
            or item.get("source_id") is None
        ]
        records.sort(key=lambda item: (item["logical_path"], item.get("source_relative") or ""))
        return _fingerprint(records)

    # ------------------------------------------------------------------
    # Durable state and task summaries
    # ------------------------------------------------------------------
    def _plan_path(self, plan_id: str) -> Path:
        if not isinstance(plan_id, str) or not plan_id or Path(plan_id).name != plan_id:
            raise ValueError("invalid plan_id")
        return self.plan_dir / f"{plan_id}.json"

    def _load_plan(self, plan_id: str) -> Dict[str, Any]:
        path = self._plan_path(plan_id)
        try:
            with path.open("r", encoding="utf-8") as handle:
                plan = json.load(handle)
        except FileNotFoundError as exc:
            raise KeyError(f"unknown transfer plan: {plan_id}") from exc
        if not isinstance(plan, dict) or plan.get("plan_version") != _PLAN_VERSION:
            raise TransferError(f"unsupported transfer plan: {plan_id}")
        return plan

    def _save_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Optional[Path] = None
        try:
            fd, raw_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
            temporary = Path(raw_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(path))
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def _save_plan(self, plan: Dict[str, Any]) -> None:
        plan["work_entries"] = [
            {
                "source_id": source["source_id"],
                "account_id": source["account_id"],
                "work_id": source["work_id"],
                "metadata": source.get("metadata") or {},
                "source_root": source.get("source_root"),
                "entry_ids": list(source.get("entry_ids") or []),
                "missing_ids": list(source.get("missing") or []),
                "bytes": sum(
                    int(entry.get("size", 0))
                    for entry in plan.get("entries") or []
                    if entry.get("source_id") == source["source_id"] and entry.get("capture", True)
                ),
            }
            for source in plan.get("sources") or []
        ]
        plan["updated_at"] = _now()
        self._save_json(self._plan_path(plan["plan_id"]), plan)
        self._write_task_index()

    def _write_task_index(self) -> None:
        summaries = self.tasks(_write_index=False)
        try:
            self._save_json(self.task_index, summaries)
        except OSError:
            # The plan itself remains authoritative.  A task index is a cache,
            # and failure to refresh it must not turn a completed copy into a
            # false failure.
            pass

    def tasks(self, _write_index: bool = True) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for path in sorted(self.plan_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    plan = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(plan, dict) or "plan_id" not in plan:
                continue
            entries = plan.get("entries") or []
            cleaned = sum(1 for item in entries if item.get("status") == "cleaned")
            copied = sum(1 for item in entries if item.get("status") in {"copied", "verified", "cleaned"})
            result.append(
                {
                    "plan_id": plan["plan_id"],
                    "state": plan.get("state", "unknown"),
                    "mode": plan.get("mode"),
                    "target": plan.get("target"),
                    "cleanup": bool(plan.get("cleanup")),
                    "created_at": plan.get("created_at"),
                    "updated_at": plan.get("updated_at"),
                    "bytes": int(plan.get("bytes", 0)),
                    "entries": len(entries),
                    "copied": copied,
                    "cleaned": cleaned,
                    "missing": len(plan.get("missing") or []),
                    "errors": len(plan.get("errors") or []),
                }
            )
        result.sort(key=lambda item: (item.get("created_at") or "", item["plan_id"]))
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(
        self,
        plan_id: str,
        activate: Optional[Callable[[Path], Any]] = None,
        should_stop: Optional[Callable[..., Any]] = None,
        progress: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]:
        plan = self._load_plan(plan_id)
        if plan.get("library_copy") or plan.get("full_library"):
            return self._execute_library_copy(plan, activate=activate,
                                              should_stop=should_stop,
                                              progress=progress)
        target = Path(plan["target"])
        copied: List[str] = []
        cleaned: List[str] = []
        errors: List[str] = []
        cleanup_errors: List[str] = []
        missing: List[Dict[str, Any]] = []
        activation_called = False

        if plan.get("state") == "completed" and not self._pending_cleanup(plan):
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        plan["state"] = "running"
        plan["last_errors"] = []
        self._save_plan(plan)
        try:
            self._validate_execution_target(plan, target)
            library = self._open_library(target)
        except Exception as exc:  # target/write setup errors must be explicit in the result
            errors.append(f"target_setup_failed: {exc}")
            plan["state"] = "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        # A transfer may be requested before any local episode directory is
        # materialized (for example a settings-only account).  Merge the
        # immutable catalog roots explicitly so settings, deleted history,
        # other accounts, and incomplete manifests travel with the plan.
        for raw_root in plan.get("library_roots") or []:
            try:
                source_library = self._open_existing_library(Path(raw_root))
                summary = library.merge_from(source_library)
                plan.setdefault("library_merges", []).append(summary)
            except Exception as exc:
                errors.append(f"library_merge_failed: {raw_root}: {exc}")
        if errors:
            plan["state"] = "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        # A source that already belongs to an immutable library is merged as a
        # library first.  Reusing its revision ID avoids creating a fresh root
        # revision (and a spurious branch) when a runtime snapshot is exported
        # again.  Legacy episode directories simply proceed through the normal
        # put_file/write_revision path below.
        for source in plan.get("sources") or []:
            if not source.get("library_root"):
                continue
            try:
                source_library = self._open_existing_library(Path(source["library_root"]))
                library.merge_from(source_library)
                work = source_library.read_work(source["account_id"], source["work_id"])
                revision = self._revision_from_work(work, source.get("library_revision_id"))
                if revision is None:
                    raise TransferError("requested library revision is absent or not a complete head")
                self._verify_projected_revision(plan, source, revision)
                source["revision_id"] = revision["revision_id"]
                source["revision_fingerprint"] = source.get("snapshot_fingerprint")
            except Exception as exc:
                errors.append(f"{source['work_id']}: library_merge_failed: {exc}")
                source["state"] = "merge_failed"
        self._save_plan(plan)

        # A dependency that was absent at preview time may have been restored
        # before a retry.  Revisit only the persisted missing paths; newly
        # discovered files in a source directory still require a fresh preview.
        self._restore_available_missing(plan)
        self._save_plan(plan)

        source_status: Dict[str, Dict[str, Any]] = {}
        for source in plan.get("sources") or []:
            status = self._revalidate_source(plan, source)
            source_status[source["source_id"]] = status
            for item in status.get("missing", []):
                self._append_missing(missing, item)
            for issue in status.get("issues", []):
                errors.append(f"{source['source_id']}: {issue}")
            if status.get("issues"):
                source["state"] = "changed" if any("changed" in issue or "new file" in issue for issue in status["issues"]) else "missing"
            else:
                source["state"] = "ready"
        self._merge_plan_missing(plan, missing)
        self._save_plan(plan)

        total = sum(1 for entry in plan.get("entries") or [] if entry.get("capture", True))
        completed_count = 0
        cancelled = False
        for entry in plan.get("entries") or []:
            if not entry.get("capture", True):
                # meta.json is canonicalised by the runtime and is never put
                # into the immutable object map, but it remains in the plan so
                # cleanup can prove the source has not changed.
                if source_status.get(entry["source_id"], {}).get("ok"):
                    entry["status"] = "verified"
                continue
            if entry.get("status") == "cleaned":
                # A cleanup-partial task may be resumed after this source
                # file has already been removed.  Its immutable object and
                # revision were verified before the unlink, so it must not be
                # treated as a changed source on the next pass.
                continue
            if source_status.get(entry["source_id"], {}).get("issues"):
                entry["status"] = "changed"
                continue
            if _call_stop(should_stop):
                cancelled = True
                break
            try:
                current = _snapshot_file(Path(entry["source_path"]))
            except _SnapshotError as exc:
                entry["status"] = "changed"
                entry["error"] = f"source_changed: {exc}"
                errors.append(f"{entry['logical_path']}: source_changed: {exc}")
                source_status[entry["source_id"]]["issues"].append("source changed during copy")
                continue
            if not _snapshot_matches(entry, current):
                entry["status"] = "changed"
                entry["error"] = "source_changed_since_preview"
                errors.append(f"{entry['logical_path']}: source_changed_since_preview")
                source_status[entry["source_id"]]["issues"].append("source changed during copy")
                continue
            try:
                resource = library.put_file(Path(entry["source_path"]))
                if not isinstance(resource, Mapping):
                    raise TransferError("ResourceLibrary.put_file returned a non-mapping")
                if resource.get("sha256") != entry["sha256"] or int(resource.get("size", -1)) != int(entry["size"]):
                    raise TransferError("destination object checksum does not match preview")
                entry["object"] = {"sha256": entry["sha256"], "size": int(entry["size"])}
                entry["status"] = "verified"
                entry["error"] = None
                copied.append(entry["logical_path"])
                completed_count += 1
                _call_progress(
                    progress,
                    {"phase": "copy", "entry": entry["logical_path"], "completed": completed_count, "total": total},
                )
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = f"copy_failed: {exc}"
                errors.append(f"{entry['logical_path']}: copy_failed: {exc}")
            self._save_plan(plan)

        if cancelled:
            plan["state"] = "cancelled"
            plan["last_errors"] = errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        # Missing source records from preview are still part of the plan.  Keep
        # them in the result even if a later source validation found no new
        # issue, until the persisted item itself has been restored.
        unresolved = list(plan.get("missing") or [])
        for item in unresolved:
            self._append_missing(missing, item)

        revisions_ready: Dict[str, Dict[str, Any]] = {}
        for source in plan.get("sources") or []:
            source_id = source["source_id"]
            status = source_status.get(source_id, {})
            source_entries = [entry for entry in plan.get("entries") or [] if entry.get("source_id") == source_id]
            if status.get("issues") or any(entry.get("status") not in {"verified", "copied"} for entry in source_entries):
                continue
            if any(item.get("source_id") == source_id for item in unresolved):
                continue
            files = {
                entry["logical_path"]: {"sha256": entry["sha256"], "size": int(entry["size"])}
                for entry in source_entries
                if entry.get("capture", True)
            }
            source_fingerprint = source.get("snapshot_fingerprint") or self._source_fingerprint(source, source_entries)
            revisions_ready[source_id] = {"source": source, "files": files, "fingerprint": source_fingerprint}

        for source_id, ready in revisions_ready.items():
            source = ready["source"]
            if _call_stop(should_stop):
                plan["state"] = "cancelled"
                self._save_plan(plan)
                return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)
            fingerprint = ready["fingerprint"]
            revision_id = source.get("revision_id") or self._find_existing_revision(
                library, source["account_id"], source["work_id"], fingerprint
            )
            if revision_id:
                source["revision_id"] = revision_id
                source["revision_fingerprint"] = fingerprint
                continue
            metadata = dict(source.get("metadata") or {})
            # This reserved field is the crash-restart idempotency marker.  It
            # is metadata, not an active source reference.
            metadata["_transfer_snapshot_fingerprint"] = fingerprint
            metadata["_transfer_plan_id"] = plan["plan_id"]
            try:
                revision = library.write_revision(
                    source["account_id"],
                    source["work_id"],
                    metadata,
                    ready["files"],
                    # A legacy/standalone source carries no trustworthy
                    # parent identity.  Treat it as an independent branch so
                    # importing a different copy cannot silently become a
                    # child of (or merge over) the current head.
                    parents=[],
                )
                revision_id = revision.get("revision_id") if isinstance(revision, Mapping) else None
                if not revision_id:
                    raise TransferError("ResourceLibrary.write_revision returned no revision_id")
                source["revision_id"] = revision_id
                source["revision_fingerprint"] = fingerprint
                plan.setdefault("created_revision_ids", []).append(revision_id)
                self._save_plan(plan)
            except Exception as exc:
                errors.append(f"{source['work_id']}: revision_write_failed: {exc}")

        # A plan with any unresolved source or copy error must never activate,
        # even when one of several works was fully copied.
        complete_sources = all(
            source.get("revision_id")
            for source in plan.get("sources") or []
            if not source.get("missing") or not any(item.get("source_id") == source["source_id"] for item in unresolved)
        )
        if unresolved or missing or errors:
            complete_sources = False
        if not complete_sources:
            plan["state"] = "incomplete" if missing or unresolved else "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        # Verify each generated revision through the catalog before switching
        # runtime configuration.  The catalog remains the authority for object
        # hashes and parent completeness.
        for source in plan.get("sources") or []:
            try:
                work = library.read_work(source["account_id"], source["work_id"])
                source_has_files = any(
                    entry.get("source_id") == source["source_id"] and entry.get("capture", True)
                    for entry in plan.get("entries") or []
                )
                allowed_states = {"available"} if source_has_files else {"available", "placeholder"}
                if work.get("state") == "conflict":
                    plan.setdefault("conflicts", []).append(
                        {
                            "account_id": source["account_id"],
                            "work_id": source["work_id"],
                            "heads": [
                                head.get("revision_id")
                                for head in (work.get("heads") or [])
                            ],
                        }
                    )
                    # A backup can contain both immutable branches and finish
                    # successfully.  Migration cannot activate or clean a
                    # conflicted work; leave it for explicit reconciliation.
                    if plan["mode"] == "backup":
                        continue
                if work.get("state") not in allowed_states:
                    raise TransferError(f"destination work state is {work.get('state')!r}")
            except Exception as exc:
                errors.append(f"{source['work_id']}: destination_verification_failed: {exc}")
        if errors:
            plan["state"] = "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        if plan["mode"] == "migration" and not plan.get("activated"):
            if activate is None:
                plan["state"] = "awaiting_activation"
                errors.append("activation callback is required for migration")
                plan["last_errors"] = errors
                self._save_plan(plan)
                return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)
            plan["activation_attempted"] = True
            self._save_plan(plan)
            activation_called = True
            try:
                result = activate(target)
                if result is False:
                    raise TransferError("activation callback returned false")
                plan["activated"] = True
            except Exception as exc:
                errors.append(f"activation_failed: {exc}")
                plan["state"] = "activation_failed"
                plan["last_errors"] = errors
                plan["errors"] = list(plan.get("errors") or []) + errors
                self._save_plan(plan)
                return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)
            self._save_plan(plan)
        elif plan["mode"] == "backup":
            plan["activated"] = False

        if plan.get("cleanup") and plan["mode"] == "migration":
            # Activation has to be true for cleanup to be reachable.  Re-read
            # the destination immediately before each unlink in _cleanup.
            cleaned, cleanup_errors, cleanup_cancelled = self._cleanup(
                plan, library, source_status, progress, should_stop
            )
            if cleanup_cancelled:
                plan["state"] = "cancelled"
            elif cleanup_errors:
                plan["state"] = "cleanup_partial"
            else:
                plan["state"] = "completed"
        else:
            plan["state"] = "completed"
        plan["last_errors"] = errors
        plan["errors"] = list(plan.get("errors") or []) + errors
        plan["cleanup_errors"] = list(plan.get("cleanup_errors") or []) + cleanup_errors
        self._save_plan(plan)
        return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

    @staticmethod
    def _pending_library_cleanup(plan: Mapping[str, Any]) -> bool:
        return bool(
            plan.get("cleanup")
            and plan.get("mode") == "migration"
            and plan.get("activated")
            and any(
                entry.get("managed") and entry.get("status") != "cleaned"
                for entry in plan.get("entries") or []
            )
        )

    def _revalidate_library_source(
        self, plan: Mapping[str, Any], source: Mapping[str, Any]
    ) -> Dict[str, Any]:
        root = Path(source["path"])
        result: Dict[str, Any] = {"ok": True, "issues": [], "missing": []}
        if root.is_symlink() or not root.exists() or not root.is_dir():
            result["ok"] = False
            result["issues"].append("library root is missing or not a directory")
            return result
        source_id = source.get("source_id")
        entries = [
            entry
            for entry in plan.get("entries") or []
            if entry.get("source_id") == source_id
        ]
        planned = {entry.get("logical_path") for entry in entries}
        for entry in entries:
            if entry.get("status") == "cleaned":
                continue
            path = Path(entry["source_path"])
            try:
                current = _snapshot_file(path)
            except _SnapshotError as exc:
                result["ok"] = False
                result["issues"].append(f"source item unavailable: {entry.get('logical_path')}: {exc}")
                result["missing"].append(
                    {
                        "source_id": source_id,
                        "logical_path": entry.get("logical_path", ""),
                        "source_path": str(path),
                        "reason": "source_missing_or_unreadable",
                        "managed": True,
                        "external": False,
                        "size": entry.get("size", 0),
                    }
                )
                continue
            if not _snapshot_matches(entry, current):
                result["ok"] = False
                result["issues"].append(f"source changed since preview: {entry.get('logical_path')}")

        # New immutable files are outside the persisted deletion/copy scope.
        # They must be handled by a fresh preview rather than silently omitted.
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if is_sync_temporary_name(path.name) or any(
                self._library_private_component(part)
                for part in PurePosixPath(relative).parts
            ):
                continue
            if is_sync_conflict_name(path.name):
                result["ok"] = False
                result["issues"].append(f"sync conflict file: {relative}")
                continue
            if relative not in planned:
                result["ok"] = False
                result["issues"].append(f"new library file since preview: {relative}")
        return result

    @staticmethod
    def _library_work_keys(plan: Mapping[str, Any]) -> List[Tuple[str, str]]:
        keys = set()
        for entry in plan.get("entries") or []:
            parts = PurePosixPath(str(entry.get("logical_path", ""))).parts
            if len(parts) == 6 and parts[0] == "accounts" and parts[2] == "works" and parts[4] == "revisions":
                keys.add((parts[1], parts[3]))
        return sorted(keys)

    def _cleanup_library_copy(
        self,
        plan: Dict[str, Any],
        source_status: Mapping[str, Mapping[str, Any]],
        progress: Optional[Callable[..., Any]],
        should_stop: Optional[Callable[..., Any]],
    ) -> Tuple[List[str], List[str], bool]:
        cleaned: List[str] = []
        errors: List[str] = []
        cancelled = False
        source_by_id = {
            source.get("source_id"): source
            for source in plan.get("library_sources") or []
        }
        for index, entry in enumerate(plan.get("entries") or [], start=1):
            if not entry.get("managed"):
                continue
            if entry.get("status") == "cleaned":
                continue
            if _call_stop(should_stop):
                cancelled = True
                errors.append("cleanup_cancelled")
                break
            source = source_by_id.get(entry.get("source_id"))
            if source is None:
                # Compatibility with a plan written before library_sources was
                # persisted: derive the root from the entry itself.
                source = {"path": entry.get("source_root"), "source_id": entry.get("source_id")}
            if source_status.get(entry.get("source_id"), {}).get("issues"):
                entry["status"] = "cleanup_refused"
                continue
            current_source = self._revalidate_library_source(plan, source)
            if current_source.get("issues"):
                entry["status"] = "cleanup_refused"
                errors.extend(
                    f"{entry.get('logical_path')}: cleanup refused; {issue}"
                    for issue in current_source["issues"]
                )
                break
            path = Path(entry["source_path"])
            try:
                if not _is_within(_canonical(path), _canonical(Path(source["path"]))):
                    raise TransferError("cleanup path escaped library root")
                current = _snapshot_file(path)
                if not _snapshot_matches(entry, current):
                    raise TransferError("cleanup refused; source changed")
                safe_unlink_verified(
                    path,
                    Path(source["path"]),
                    str(entry["sha256"]),
                    int(entry["size"]),
                )
                entry["status"] = "cleaned"
                cleaned.append(entry["logical_path"])
            except FileNotFoundError:
                entry["status"] = "cleaned"
                cleaned.append(entry["logical_path"])
            except Exception as exc:
                entry["status"] = "cleanup_refused"
                errors.append(f"{entry.get('logical_path')}: {exc}")
            self._save_plan(plan)
            if entry.get("status") == "cleaned":
                try:
                    _call_progress(
                        progress,
                        {
                            "phase": "cleanup",
                            "entry": entry.get("logical_path"),
                            "completed": index,
                            "total": len(plan.get("entries") or []),
                        },
                    )
                except Exception as exc:
                    errors.append(f"{entry.get('logical_path')}: progress_failed: {exc}")
                    break
        return cleaned, errors, cancelled

    def _execute_library_copy(
        self,
        plan: Dict[str, Any],
        activate: Optional[Callable[[Path], Any]] = None,
        should_stop: Optional[Callable[..., Any]] = None,
        progress: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a byte-for-byte catalog plan with resumable verification."""

        target = Path(plan["target"])
        copied: List[str] = []
        cleaned: List[str] = []
        errors: List[str] = []
        cleanup_errors: List[str] = []
        missing: List[Dict[str, Any]] = [dict(item) for item in plan.get("missing") or []]

        if plan.get("state") == "completed" and not self._pending_library_cleanup(plan):
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        plan["state"] = "running"
        plan["last_errors"] = []
        self._save_plan(plan)

        source_records = list(plan.get("library_sources") or [])
        if not source_records:
            # Plans written by the earlier single-root implementation are
            # still executable after a process restart.
            for index, raw_root in enumerate(plan.get("library_roots") or []):
                source_records.append(
                    {
                        "source_id": "library-copy" if index == 0 else f"library-copy-{index}",
                        "path": str(raw_root),
                        "source_root": str(raw_root),
                        "library_root": str(raw_root),
                        "library_id": None,
                        "entry_ids": [
                            entry.get("entry_id")
                            for entry in plan.get("entries") or []
                            if entry.get("source_id") in {"library-copy", f"library-copy-{index}"}
                        ],
                        "missing": [],
                        "state": "planned",
                    }
                )
            if source_records:
                for entry in plan.get("entries") or []:
                    entry.setdefault("source_id", source_records[0]["source_id"])

        source_status: Dict[str, Dict[str, Any]] = {}
        try:
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise TransferError("target must be a directory")
            target.mkdir(parents=True, exist_ok=True)
            for source in source_records:
                status = self._revalidate_library_source(plan, source)
                source_status[source["source_id"]] = status
                for item in status.get("missing", []):
                    self._append_missing(missing, item)
                errors.extend(
                    f"{source.get('source_id')}: {issue}"
                    for issue in status.get("issues", [])
                )
                source["state"] = "ready" if status.get("ok") else "changed"
            self._merge_plan_missing(plan, missing)
            self._save_plan(plan)
        except Exception as exc:
            errors.append(f"target_setup_failed: {exc}")

        # A source with an invalid manifest/object graph cannot be copied as a
        # completed catalog.  Keeping the plan and any already verified target
        # files makes a later, corrected preview or resume explicit.
        if missing or errors:
            plan["state"] = "incomplete" if missing else "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        total = len(plan.get("entries") or [])
        done = 0
        cancelled = False
        for entry in plan.get("entries") or []:
            if entry.get("status") == "cleaned":
                continue
            if _call_stop(should_stop):
                cancelled = True
                break
            source_id = entry.get("source_id")
            if source_status.get(source_id, {}).get("issues"):
                continue
            source_path = Path(entry["source_path"])
            try:
                logical_path = _safe_logical_path(entry.get("logical_path"))
                destination = target.joinpath(*logical_path.split("/"))
                current = _snapshot_file(source_path)
                if not _snapshot_matches(entry, current):
                    raise TransferError(f"source_changed_since_preview: {entry['logical_path']}")
                if destination.exists() or destination.is_symlink():
                    if destination.is_symlink() or not destination.is_file():
                        raise TransferError(f"destination collision: {entry['logical_path']}")
                    existing = _snapshot_file(destination)
                    # The library descriptor is the identity of the source
                    # catalog.  A pre-existing target may legitimately have a
                    # different library ID; preserve the target's identity.
                    if entry.get("logical_path") == "library.json":
                        self._open_existing_library(target)
                    elif (
                        existing["sha256"] != entry["sha256"]
                        or int(existing["size"]) != int(entry["size"])
                    ):
                        raise TransferError(f"destination collision: {entry['logical_path']}")
                else:
                    self._ensure_library_copy_parent(target, destination.parent)
                    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
                    try:
                        with source_path.open("rb") as source_stream, temporary.open("xb") as target_stream:
                            import shutil as _shutil

                            _shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                            target_stream.flush()
                            os.fsync(target_stream.fileno())
                        os.replace(temporary, destination)
                    finally:
                        try:
                            temporary.unlink()
                        except FileNotFoundError:
                            pass
                    copied.append(logical_path)
                entry["status"] = "verified"
                entry["error"] = None
                done += 1
                _call_progress(
                    progress,
                    {
                        "phase": "copy",
                        "entry": logical_path,
                        "completed": done,
                        "total": total,
                    },
                )
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)
                errors.append(str(exc))
            self._save_plan(plan)

        if cancelled:
            plan["state"] = "cancelled"
            plan["last_errors"] = errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)
        if errors or any(entry.get("status") not in {"verified", "cleaned"} for entry in plan.get("entries") or []):
            plan["state"] = "failed"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        # Reopen and walk the destination after copying.  This verifies every
        # referenced object and manifest through the catalog, including files
        # which arrived out of order before the plan started.
        try:
            destination_library = self._open_existing_library(target)
            destination_library.list_works()
            destination_library._iter_object_paths([])
            destination_library._iter_manifest_paths([])
            for key in self._library_work_keys(plan):
                work = destination_library.read_work(*key)
                if work.get("state") == "pending":
                    raise TransferError(f"destination work {key[1]} remains incomplete")
        except Exception as exc:
            errors.append(f"destination_validation_failed: {exc}")
            plan["state"] = "incomplete"
            plan["last_errors"] = errors
            plan["errors"] = list(plan.get("errors") or []) + errors
            self._save_plan(plan)
            return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        if plan.get("mode") == "migration" and not plan.get("activated"):
            if activate is None:
                errors.append("activation callback is required for migration")
                plan["state"] = "awaiting_activation"
                plan["last_errors"] = errors
                self._save_plan(plan)
                return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)
            plan["activation_attempted"] = True
            try:
                result = activate(target)
                if result is False:
                    raise TransferError("activation callback returned false")
                plan["activated"] = True
            except Exception as exc:
                errors.append(f"activation_failed: {exc}")
                plan["state"] = "activation_failed"
                plan["last_errors"] = errors
                plan["errors"] = list(plan.get("errors") or []) + errors
                self._save_plan(plan)
                return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

        if plan.get("cleanup") and plan.get("mode") == "migration":
            cleaned, cleanup_errors, cancelled = self._cleanup_library_copy(
                plan, source_status, progress, should_stop
            )
            if cancelled:
                plan["state"] = "cancelled"
            elif cleanup_errors:
                plan["state"] = "cleanup_partial"
            else:
                plan["state"] = "completed"
        else:
            plan["state"] = "completed"
        plan["last_errors"] = errors
        plan["errors"] = list(plan.get("errors") or []) + errors
        plan["cleanup_errors"] = list(plan.get("cleanup_errors") or []) + cleanup_errors
        self._save_plan(plan)
        return self._result(plan, copied, cleaned, missing, errors, cleanup_errors)

    @staticmethod
    def _ensure_library_copy_parent(root: Path, parent: Path) -> None:
        """Create a copy destination only through non-symlink directories."""

        root = Path(root)
        parent = Path(parent)
        try:
            parent.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as exc:
            raise TransferError("destination path escapes target") from exc
        current = parent
        while True:
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise TransferError("destination path contains a symlink or file")
            if current == root or current.parent == current:
                break
            current = current.parent
        parent.mkdir(parents=True, exist_ok=True)

    def _open_library(self, target: Path) -> Any:
        from .catalog import ResourceLibrary

        return ResourceLibrary(target, create=True)

    def _open_existing_library(self, root: Path) -> Any:
        from .catalog import ResourceLibrary

        return ResourceLibrary(root, create=False)

    @staticmethod
    def _revision_from_work(work: Mapping[str, Any], revision_id: Optional[str]) -> Optional[Mapping[str, Any]]:
        if not revision_id:
            return None
        for candidate in list(work.get("heads") or []) + ([work.get("revision")] if work.get("revision") else []):
            if isinstance(candidate, Mapping) and candidate.get("revision_id") == revision_id:
                if work.get("state") in {"available", "placeholder", "deleted"}:
                    return candidate
        return None

    @staticmethod
    def _verify_projected_revision(
        plan: Mapping[str, Any], source: Mapping[str, Any], revision: Mapping[str, Any]
    ) -> None:
        """Ensure a reused library revision describes the files in this plan."""

        expected = {
            entry["logical_path"]: {"sha256": entry["sha256"], "size": int(entry["size"])}
            for entry in plan.get("entries") or []
            if entry.get("source_id") == source.get("source_id") and entry.get("capture", True)
        }
        actual = revision.get("files") or {}
        if actual != expected:
            raise TransferError("library revision files do not match the transfer snapshot")
        metadata = revision.get("metadata") or {}
        requested = source.get("metadata") or {}
        # The runtime may have added canonical metadata fields since a legacy
        # source descriptor was created.  Require caller-provided fields to
        # agree, while allowing the catalog's default ``kind`` and the
        # transfer idempotency markers.
        for key, value in requested.items():
            if key.startswith("_"):
                continue
            if metadata.get(key) != value:
                raise TransferError(f"library revision metadata differs for {key}")

    def _validate_execution_target(self, plan: Mapping[str, Any], target: Path) -> None:
        if target.exists() and target.is_file():
            raise TransferError("target is a file")
        for source in plan.get("sources") or []:
            root = _canonical(Path(source["path"]))
            if _same_or_nested(root, target):
                raise TransferError("source and target became equal or nested")

    def _restore_available_missing(self, plan: Dict[str, Any]) -> None:
        restored: List[Dict[str, Any]] = []
        remaining: List[Dict[str, Any]] = []
        entries = plan.setdefault("entries", [])
        sources = {source["source_id"]: source for source in plan.get("sources") or []}
        for item in plan.get("missing") or []:
            path_value = item.get("source_path")
            source = sources.get(item.get("source_id"))
            if not path_value or not source or item.get("reason") in {
                "source_missing",
                "source_not_directory",
                "symlink_not_followed",
            }:
                remaining.append(item)
                continue
            path = Path(path_value)
            if path.is_symlink() or not path.exists() or not path.is_file():
                remaining.append(item)
                continue
            try:
                snapshot = _snapshot_file(path)
                logical = _safe_logical_path(item.get("logical_path", ""))
            except (ValueError, _SnapshotError):
                remaining.append(item)
                continue
            entry = {
                "entry_id": uuid.uuid4().hex,
                "source_id": source["source_id"],
                "account_id": source["account_id"],
                "work_id": source["work_id"],
                "metadata": source.get("metadata") or {},
                "source_root": source["source_root"],
                "logical_path": logical,
                "source_path": str(path.resolve(strict=False)),
                "source_relative": item.get("source_relative"),
                "external": bool(item.get("external", True)),
                "managed": bool(item.get("managed", False)),
                "capture": True,
                "cleanup_only": False,
                "status": "planned",
                "error": None,
                **snapshot,
            }
            entry["path"] = entry["source_path"]
            entry["destination"] = entry["logical_path"]
            entry["target"] = entry["logical_path"]
            entries.append(entry)
            source.setdefault("entry_ids", []).append(entry["entry_id"])
            if entry["managed"] and entry.get("source_relative"):
                source.setdefault("managed_paths", []).append(entry["source_relative"])
            restored.append(item)
        if restored:
            plan["missing"] = remaining
            plan["bytes"] = sum(
                int(entry.get("size", 0)) for entry in entries if entry.get("capture", True)
            )
            plan["bytes_total"] = plan["bytes"]
            plan["bytes_available"] = plan["bytes"]
            plan["bytes_missing"] = sum(int(item.get("size", 0)) for item in remaining)
            plan["byte_count"] = plan["bytes"]
            for source in plan.get("sources") or []:
                source_entries = [
                    entry for entry in entries if entry.get("source_id") == source.get("source_id")
                ]
                source["snapshot_fingerprint"] = self._source_fingerprint(source, source_entries)
            plan["snapshot_fingerprint"] = _fingerprint(
                [
                    {
                        "account_id": source["account_id"],
                        "work_id": source["work_id"],
                        "fingerprint": source.get("snapshot_fingerprint"),
                    }
                    for source in plan.get("sources") or []
                ]
            )

    def _revalidate_source(self, plan: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
        root = Path(source["path"])
        result: Dict[str, Any] = {"ok": True, "issues": [], "missing": [], "current": {}}
        if root.is_symlink() or not root.exists() or not root.is_dir():
            result["ok"] = False
            result["issues"].append("source directory is missing or not a directory")
            for entry in plan.get("entries") or []:
                if entry.get("source_id") == source["source_id"] and entry.get("managed"):
                    result["missing"].append(
                        {
                            "source_id": source["source_id"],
                            "account_id": source["account_id"],
                            "work_id": source["work_id"],
                            "logical_path": entry.get("logical_path", ""),
                            "source_path": entry.get("source_path"),
                            "reason": "source_missing",
                            "managed": True,
                            "external": False,
                            "size": entry.get("size", 0),
                            "sha256": entry.get("sha256"),
                        }
                    )
            return result

        scanned, scan_missing = self._scan_root(source, root)
        current_by_relative = {
            item.get("source_relative"): item for item in scanned if item.get("source_relative")
        }
        planned_relative = {
            entry.get("source_relative")
            for entry in plan.get("entries") or []
            if entry.get("source_id") == source["source_id"]
            and entry.get("managed")
            and entry.get("source_relative")
            and entry.get("status") != "cleaned"
        }
        for item in scan_missing:
            if item.get("reason") != "excluded_sensitive_file":
                result["missing"].append(
                    {
                        "source_id": source["source_id"],
                        "account_id": source["account_id"],
                        "work_id": source["work_id"],
                        **item,
                    }
                )
                result["ok"] = False
                result["issues"].append(f"source item unavailable: {item.get('logical_path', '')}")
        for relative in sorted(set(current_by_relative) - planned_relative):
            result["ok"] = False
            result["issues"].append(f"new file since preview: {relative}")
        for entry in plan.get("entries") or []:
            if entry.get("source_id") != source["source_id"] or not entry.get("managed"):
                continue
            if entry.get("status") == "cleaned":
                continue
            relative = entry.get("source_relative")
            current = current_by_relative.get(relative)
            if current is None:
                result["ok"] = False
                result["issues"].append(f"source file missing: {relative}")
                result["missing"].append(
                    {
                        "source_id": source["source_id"],
                        "account_id": source["account_id"],
                        "work_id": source["work_id"],
                        "logical_path": entry.get("logical_path", ""),
                        "source_path": entry.get("source_path"),
                        "reason": "source_missing",
                        "managed": True,
                        "external": False,
                        "size": entry.get("size", 0),
                        "sha256": entry.get("sha256"),
                    }
                )
                continue
            result["current"][entry["entry_id"]] = current
            if not _snapshot_matches(entry, current):
                result["ok"] = False
                result["issues"].append(f"source changed since preview: {relative}")

        # Explicit external dependencies must be rechecked too, but can never
        # become part of the deletion scope.
        for entry in plan.get("entries") or []:
            if entry.get("source_id") != source["source_id"] or entry.get("managed"):
                continue
            path = Path(entry["source_path"])
            try:
                current = _snapshot_file(path)
            except _SnapshotError as exc:
                result["ok"] = False
                result["issues"].append(f"external dependency changed or missing: {entry['logical_path']}: {exc}")
                result["missing"].append(
                    {
                        "source_id": source["source_id"],
                        "account_id": source["account_id"],
                        "work_id": source["work_id"],
                        "logical_path": entry.get("logical_path", ""),
                        "source_path": entry.get("source_path"),
                        "reason": "dependency_missing_or_changed",
                        "managed": False,
                        "external": True,
                    }
                )
                continue
            result["current"][entry["entry_id"]] = current
            if not _snapshot_matches(entry, current):
                result["ok"] = False
                result["issues"].append(f"external dependency changed: {entry['logical_path']}")
        return result

    @staticmethod
    def _append_missing(target: List[Dict[str, Any]], item: Mapping[str, Any]) -> None:
        key = (item.get("source_id"), item.get("logical_path"), item.get("reason"), item.get("source_path"))
        if not any(
            (existing.get("source_id"), existing.get("logical_path"), existing.get("reason"), existing.get("source_path")) == key
            for existing in target
        ):
            target.append(dict(item))

    def _merge_plan_missing(self, plan: Dict[str, Any], current: Sequence[Mapping[str, Any]]) -> None:
        merged: List[Dict[str, Any]] = []
        for item in list(plan.get("missing") or []) + [dict(value) for value in current]:
            self._append_missing(merged, item)
        plan["missing"] = merged
        plan["bytes_missing"] = sum(int(item.get("size", 0)) for item in merged)

    def _find_existing_revision(self, library: Any, account_id: str, work_id: str, fingerprint: str) -> Optional[str]:
        try:
            work = library.read_work(account_id, work_id)
        except Exception:
            return None
        candidates: List[Any] = []
        if isinstance(work, Mapping):
            candidates.extend(work.get("heads") or [])
            if work.get("revision"):
                candidates.append(work["revision"])
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                metadata = candidate.get("metadata") or {}
                if metadata.get("_transfer_snapshot_fingerprint") == fingerprint:
                    return candidate.get("revision_id")
        return None

    @staticmethod
    def _pending_cleanup(plan: Mapping[str, Any]) -> bool:
        return bool(
            plan.get("cleanup")
            and plan.get("mode") == "migration"
            and plan.get("activated")
            and any(
                entry.get("managed") and entry.get("status") not in {"cleaned", "preserved"}
                for entry in plan.get("entries") or []
            )
        )

    def _cleanup(
        self,
        plan: Dict[str, Any],
        library: Any,
        source_status: Mapping[str, Mapping[str, Any]],
        progress: Optional[Callable[..., Any]],
        should_stop: Optional[Callable[..., Any]] = None,
    ) -> Tuple[List[str], List[str], bool]:
        cleaned: List[str] = []
        errors: List[str] = []
        cancelled = False
        managed_entries = [entry for entry in plan.get("entries") or [] if entry.get("managed")]
        source_by_id = {source["source_id"]: source for source in plan.get("sources") or []}
        for index, entry in enumerate(managed_entries, start=1):
            if _call_stop(should_stop):
                cancelled = True
                errors.append("cleanup_cancelled")
                break
            source_id = entry["source_id"]
            if source_status.get(source_id, {}).get("issues"):
                entry["status"] = "cleanup_refused"
                continue
            if entry.get("status") == "cleaned":
                continue
            source = source_by_id.get(source_id)
            if source is None:
                entry["status"] = "cleanup_refused"
                errors.append(f"{entry.get('logical_path')}: cleanup source disappeared from plan")
                continue
            # Re-scan the managed source before every unlink.  This catches a
            # file created between two cleanup operations and prevents the
            # task from deleting an older file in that same source afterward.
            current_source = self._revalidate_source(plan, source)
            if current_source.get("issues"):
                entry["status"] = "cleanup_refused"
                errors.extend(
                    f"{entry.get('logical_path')}: cleanup refused; {issue}"
                    for issue in current_source["issues"]
                )
                break
            # Revalidate target and source for every unlink.  This narrows the
            # race window and makes a resumed task's deletion scope explicit.
            try:
                self._validate_execution_target(plan, Path(plan["target"]))
                self._verify_plan_destination(plan, library)
                current = _snapshot_file(Path(entry["source_path"]))
            except Exception as exc:
                entry["status"] = "cleanup_refused"
                errors.append(f"{entry.get('logical_path', entry.get('source_path'))}: cleanup verification failed: {exc}")
                self._save_plan(plan)
                continue
            if not _snapshot_matches(entry, current):
                entry["status"] = "cleanup_refused"
                errors.append(f"{entry.get('logical_path')}: cleanup refused; source changed")
                self._save_plan(plan)
                continue
            source_path = Path(entry["source_path"])
            try:
                if source_path.is_symlink() or not _is_within(_canonical(source_path), _canonical(Path(entry["source_root"]))):
                    raise TransferError("cleanup path escaped source root")
                safe_unlink_verified(
                    source_path,
                    Path(entry["source_root"]),
                    str(entry["sha256"]),
                    int(entry["size"]),
                )
                entry["status"] = "cleaned"
                cleaned.append(entry["logical_path"])
            except Exception as exc:
                entry["status"] = "cleanup_error"
                errors.append(f"{entry.get('logical_path')}: cleanup_failed: {exc}")
            self._save_plan(plan)
            if entry.get("status") == "cleaned":
                try:
                    _call_progress(
                        progress,
                        {
                            "phase": "cleanup",
                            "entry": entry["logical_path"],
                            "completed": index,
                            "total": len(managed_entries),
                        },
                    )
                except Exception as exc:
                    # The deletion has already been durably recorded.  A UI
                    # progress callback failing must not turn that item into
                    # an unsafe retry, but it is still surfaced as a partial
                    # task error for the caller.
                    errors.append(f"{entry.get('logical_path')}: progress_failed: {exc}")
                    break
        return cleaned, errors, cancelled

    def _verify_plan_destination(self, plan: Mapping[str, Any], library: Any) -> None:
        for source in plan.get("sources") or []:
            if not source.get("revision_id"):
                raise TransferError(f"work {source.get('work_id')} has no revision")
            work = library.read_work(source["account_id"], source["work_id"])
            source_has_files = any(
                entry.get("source_id") == source["source_id"] and entry.get("capture", True)
                for entry in plan.get("entries") or []
            )
            allowed_states = {"available"} if source_has_files else {"available", "placeholder"}
            if work.get("state") not in allowed_states:
                raise TransferError(f"work {source.get('work_id')} is {work.get('state')!r}")

    def _result(
        self,
        plan: Mapping[str, Any],
        copied: Sequence[str],
        cleaned: Sequence[str],
        missing: Sequence[Mapping[str, Any]],
        errors: Sequence[str],
        cleanup_errors: Sequence[str],
    ) -> Dict[str, Any]:
        return {
            "plan_id": plan.get("plan_id"),
            "state": plan.get("state"),
            "mode": plan.get("mode"),
            "target": plan.get("target"),
            "copied": list(copied),
            "cleaned": list(cleaned),
            "missing": [dict(item) for item in missing],
            "errors": list(errors),
            "cleanup_errors": list(cleanup_errors),
            "created_revision_ids": list(plan.get("created_revision_ids") or []),
            "conflicts": [dict(item) for item in plan.get("conflicts") or []],
            "library_roots": list(plan.get("library_roots") or []),
            "object_count": int(plan.get("object_count", 0)),
            "manifest_count": int(plan.get("manifest_count", 0)),
            "activated": bool(plan.get("activated")),
        }
