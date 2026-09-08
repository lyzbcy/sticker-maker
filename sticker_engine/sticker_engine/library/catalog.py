"""Immutable account/work resource catalog.

The directory is intentionally a set of immutable objects and revision
manifests.  There is no mutable HEAD file: a work's active state is derived
from the revision graph and the objects each revision references.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .resources import (
    atomic_write_bytes,
    hash_file,
    is_sync_conflict_name,
    is_sync_temporary_name,
    validate_episode_metadata_paths,
    validate_settings_metadata_paths,
    validate_case_unique,
    validate_hash,
    validate_identifier,
    validate_logical_path,
)


class LibraryError(Exception):
    """Base exception for catalog failures."""


class LibraryValidationError(LibraryError, ValueError):
    """Malformed or unsafe catalog input."""


class LibraryIntegrityError(LibraryError):
    """A content-addressed object does not match its declared identity."""


class LibraryCollisionError(LibraryError):
    """An immutable object or manifest identity has different content."""


class LibraryStateError(LibraryError):
    """A requested operation needs a complete, non-conflicting revision."""


Revision = Dict[str, Any]
Work = Dict[str, Any]


class ResourceLibrary:
    """Read and write an immutable resource library rooted at ``root``."""

    FORMAT = "sticker-engine-resource-library"
    SCHEMA_VERSION = 1

    def __init__(self, root: Union[str, Path], create: bool = False):
        self._root = Path(root).expanduser()
        self._verified_objects: Dict[str, Tuple[Path, int, int, int, int, int]] = {}
        library_file = self._root / "library.json"
        if create:
            self._root.mkdir(parents=True, exist_ok=True)
        if not self._root.exists() or not self._root.is_dir():
            raise FileNotFoundError(self._root)
        if library_file.is_symlink():
            raise LibraryValidationError("library.json must not be a symlink")
        if library_file.exists():
            document = self._read_json(library_file, "library.json")
            self._library_id = self._validate_library_document(document)
        elif create:
            self._library_id = str(uuid.uuid4())
            document = {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "library_id": self._library_id,
            }
            atomic_write_bytes(library_file, self._json_bytes(document))
        else:
            raise FileNotFoundError(library_file)
        if create:
            self._ensure_directory_layout()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def library_id(self) -> str:
        return self._library_id

    # ------------------------------------------------------------------
    # Public object/revision API
    # ------------------------------------------------------------------
    def put_file(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Store ``path`` under its SHA-256 content identity."""

        source = Path(path)
        try:
            digest, size = hash_file(source)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc
        self._ensure_object_directories(digest)
        destination = self._object_path(digest)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise LibraryValidationError(f"object path is not a regular file: {destination}")
            actual_hash, actual_size = hash_file(destination)
            if actual_hash != digest or actual_size != size:
                raise LibraryIntegrityError(f"corrupt object: {digest}")
        else:
            temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                    target_stream.flush()
                    os.fsync(target_stream.fileno())
                os.replace(temporary, destination)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
        return {"sha256": digest, "size": size}

    def write_revision(
        self,
        account_id: str,
        work_id: str,
        metadata: Mapping[str, Any],
        files: Mapping[str, Mapping[str, Any]],
        parents: Optional[Sequence[str]] = None,
        deleted: bool = False,
    ) -> Revision:
        account_id = self._safe_id(account_id, "account_id")
        work_id = self._safe_id(work_id, "work_id")
        metadata_copy = self._validate_metadata(metadata)
        files_copy = self._validate_files(files)
        if not isinstance(deleted, bool):
            raise LibraryValidationError("deleted must be a boolean")
        for resource in files_copy.values():
            self._require_object(resource["sha256"], resource["size"])

        if parents is None:
            snapshot, _parsed, _complete = self._analyze_work(account_id, work_id)
            if snapshot["state"] != "pending":
                parent_ids = [head["revision_id"] for head in snapshot["heads"]]
            else:
                parent_ids = []
        else:
            if isinstance(parents, (str, bytes)):
                raise LibraryValidationError("parents must be a sequence of ids")
            parent_ids = []
            for parent in parents:
                parent_id = self._safe_id(parent, "parent revision id")
                if parent_id in parent_ids:
                    raise LibraryValidationError("duplicate parent revision")
                parent_ids.append(parent_id)
            _snapshot, parsed, complete = self._analyze_work(account_id, work_id)
            for parent_id in parent_ids:
                if parent_id not in parsed:
                    raise LibraryValidationError(f"missing parent revision: {parent_id}")
                if not complete.get(parent_id, (False, ()))[0]:
                    raise LibraryValidationError(f"incomplete parent revision: {parent_id}")

        revision: Revision = {
            "schema_version": self.SCHEMA_VERSION,
            "revision_id": str(uuid.uuid4()),
            "account_id": account_id,
            "work_id": work_id,
            "metadata": metadata_copy,
            "files": files_copy,
            "parents": parent_ids,
            "deleted": deleted,
        }
        destination = self._revision_path(account_id, work_id, revision["revision_id"])
        self._ensure_revision_directories(account_id, work_id)
        if destination.exists() or destination.is_symlink():
            raise LibraryCollisionError(f"revision already exists: {revision['revision_id']}")
        atomic_write_bytes(destination, self._json_bytes(revision))
        return copy.deepcopy(revision)

    def read_work(self, account_id: str, work_id: str) -> Work:
        account_id = self._safe_id(account_id, "account_id")
        work_id = self._safe_id(work_id, "work_id")
        snapshot, _parsed, _complete = self._analyze_work(account_id, work_id)
        return copy.deepcopy(snapshot)

    def list_works(self, account_id: Optional[str] = None) -> List[Work]:
        if account_id is not None:
            account_id = self._safe_id(account_id, "account_id")
            accounts = [account_id]
        else:
            accounts_dir = self._root / "accounts"
            if not accounts_dir.exists():
                return []
            self._reject_symlink(accounts_dir, "accounts")
            accounts = []
            for entry in accounts_dir.iterdir():
                if is_sync_conflict_name(entry.name) or is_sync_temporary_name(entry.name):
                    continue
                if entry.is_symlink() or not entry.is_dir():
                    raise LibraryValidationError(f"unexpected account entry: {entry.name}")
                accounts.append(self._safe_id(entry.name, "account_id"))
            self._ensure_case_unique(accounts, "account ids")
            accounts.sort()

        result: List[Work] = []
        for current_account in accounts:
            account_dir = self._root / "accounts" / current_account
            if not account_dir.exists():
                continue
            self._reject_symlink(account_dir, "account directory")
            works_dir = account_dir / "works"
            if not works_dir.exists():
                continue
            self._reject_symlink(works_dir, "works directory")
            work_names = []
            for entry in sorted(works_dir.iterdir(), key=lambda item: item.name):
                if is_sync_conflict_name(entry.name) or is_sync_temporary_name(entry.name):
                    continue
                if entry.is_symlink() or not entry.is_dir():
                    raise LibraryValidationError(f"unexpected work entry: {entry.name}")
                current_work = self._safe_id(entry.name, "work_id")
                work_names.append(current_work)
                result.append(self.read_work(current_account, current_work))
            self._ensure_case_unique(work_names, "work ids")
        return result

    def materialize(
        self,
        account_id: str,
        work_id: str,
        target: Union[str, Path],
        revision_id: Optional[str] = None,
    ) -> Path:
        account_id = self._safe_id(account_id, "account_id")
        work_id = self._safe_id(work_id, "work_id")
        if revision_id is not None:
            revision_id = self._safe_id(revision_id, "revision_id")
        snapshot, parsed, complete = self._analyze_work(account_id, work_id)
        if revision_id is None:
            if snapshot["state"] == "pending":
                raise LibraryStateError("work resources are still pending")
            if snapshot["state"] == "conflict":
                raise LibraryStateError("work has conflicting heads")
            if snapshot["revision"] is None:
                raise LibraryStateError("work has no materializable revision")
            revision_id = snapshot["revision"]["revision_id"]
        revision = parsed.get(revision_id)
        if revision is None:
            raise FileNotFoundError(f"revision {revision_id}")
        status, missing = complete.get(revision_id, (False, ()))
        if not status:
            raise LibraryValidationError(
                f"revision {revision_id} is incomplete: {', '.join(missing)}"
            )
        if revision["deleted"]:
            raise LibraryStateError("deleted revisions cannot be materialized")

        output = Path(target).expanduser()
        self._prepare_materialize_target(output)
        # An existing, empty dedicated target can be populated in place.  A
        # missing target is staged and renamed only after all data is verified.
        staged = output if output.exists() else output.parent / f".{output.name}.materialize-{uuid.uuid4().hex}"
        if not output.exists():
            staged.mkdir(parents=True, exist_ok=False)
        try:
            for logical_path, resource in revision["files"].items():
                destination = self._safe_materialized_destination(staged, logical_path)
                if destination.exists() or destination.is_symlink():
                    raise LibraryValidationError(f"materialize target already contains: {logical_path}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._reject_path_symlinks(staged, destination.parent)
                self._copy_verified_object(resource["sha256"], resource["size"], destination)
            if staged is not output:
                if output.exists():
                    raise LibraryValidationError("materialize target appeared during staging")
                os.replace(staged, output)
        except Exception:
            if staged is not output:
                shutil.rmtree(staged, ignore_errors=True)
            raise
        return output

    def merge_from(self, source: Union["ResourceLibrary", str, Path]) -> Dict[str, Any]:
        if isinstance(source, ResourceLibrary):
            other = source
        else:
            other = ResourceLibrary(source, create=False)
        summary: Dict[str, Any] = {
            "library_id": other.library_id,
            "objects": 0,
            "revisions": 0,
            "existing_objects": 0,
            "existing_revisions": 0,
            "sync_conflicts": [],
        }
        if other.root == self.root:
            return summary

        for object_path in other._iter_object_paths(summary["sync_conflicts"]):
            relative = object_path.relative_to(other.root)
            destination = self._root / relative
            if self._copy_object_immutable(object_path, destination):
                summary["objects"] += 1
            else:
                summary["existing_objects"] += 1

        for manifest_path, account_id, work_id, revision_id in other._iter_manifest_paths(
            summary["sync_conflicts"]
        ):
            relative = manifest_path.relative_to(other.root)
            destination = self._root / relative
            # Parse before copying so an unsafe or malformed source cannot
            # become a trusted target manifest.
            other._load_revision(manifest_path, account_id, work_id, revision_id)
            if self._copy_manifest_immutable(manifest_path, destination):
                summary["revisions"] += 1
            else:
                summary["existing_revisions"] += 1
        return summary

    def resolve(self, account_id: str, work_id: str, revision_id: str) -> Revision:
        account_id = self._safe_id(account_id, "account_id")
        work_id = self._safe_id(work_id, "work_id")
        revision_id = self._safe_id(revision_id, "revision_id")
        snapshot, parsed, complete = self._analyze_work(account_id, work_id)
        if snapshot["state"] != "conflict":
            raise LibraryStateError("work has no conflicting heads")
        selected = parsed.get(revision_id)
        if selected is None:
            raise FileNotFoundError(f"revision {revision_id}")
        if not complete.get(revision_id, (False, ()))[0]:
            raise LibraryValidationError("selected revision is incomplete")
        parents = [head["revision_id"] for head in snapshot["heads"]]
        return self.write_revision(
            account_id,
            work_id,
            selected["metadata"],
            selected["files"],
            parents=parents,
            deleted=selected["deleted"],
        )

    # ------------------------------------------------------------------
    # Catalog validation and graph analysis
    # ------------------------------------------------------------------
    def _analyze_work(
        self, account_id: str, work_id: str
    ) -> Tuple[Work, Dict[str, Revision], Dict[str, Tuple[bool, Tuple[str, ...]]]]:
        self._ensure_work_path_components(account_id, work_id)
        revisions_dir = self._revision_dir(account_id, work_id)
        if not revisions_dir.exists():
            return self._empty_work(account_id, work_id), {}, {}
        self._reject_symlink(revisions_dir, "revisions directory")
        parsed: Dict[str, Revision] = {}
        sync_conflicts: List[str] = []
        revision_names: List[str] = []
        for entry in sorted(revisions_dir.iterdir(), key=lambda item: item.name):
            relative = str(entry.relative_to(self._root))
            if is_sync_conflict_name(entry.name):
                sync_conflicts.append(relative)
                continue
            if is_sync_temporary_name(entry.name):
                continue
            if entry.is_symlink():
                raise LibraryValidationError(f"revision entry is a symlink: {relative}")
            if entry.is_dir():
                raise LibraryValidationError(f"unexpected revision directory: {relative}")
            if entry.suffix != ".json":
                continue
            revision_id = entry.stem
            revision_names.append(revision_id)
            parsed[revision_id] = self._load_revision(entry, account_id, work_id, revision_id)
        self._ensure_case_unique(revision_names, "revision ids")
        if not parsed:
            result = self._empty_work(account_id, work_id)
            result["sync_conflicts"] = sync_conflicts
            return result, {}, {}

        self._validate_graph(parsed)
        complete: Dict[str, Tuple[bool, Tuple[str, ...]]] = {}
        for revision_id in parsed:
            self._revision_complete(revision_id, parsed, complete, set())
        referenced = {parent for revision in parsed.values() for parent in revision["parents"]}
        head_ids = sorted(revision_id for revision_id in parsed if revision_id not in referenced)
        heads = [parsed[revision_id] for revision_id in head_ids]
        complete_heads = [revision for revision in heads if complete[revision["revision_id"]][0]]
        incomplete_heads = [revision for revision in heads if not complete[revision["revision_id"]][0]]
        missing: List[str] = []
        for revision in incomplete_heads:
            missing.extend(complete[revision["revision_id"]][1])
        missing = sorted(set(missing))

        if incomplete_heads:
            state = "pending"
            active_revision = None
        elif len(complete_heads) > 1:
            state = "conflict"
            active_revision = None
        else:
            active_revision = complete_heads[0] if complete_heads else None
            if active_revision is None:
                state = "pending"
            elif active_revision["deleted"]:
                state = "deleted"
            elif (
                active_revision["metadata"].get("state") == "placeholder"
                or active_revision["metadata"].get("resource_placeholder") is True
                or (
                    active_revision["metadata"].get("kind", "episode") == "episode"
                    and not active_revision["files"]
                )
            ):
                state = "placeholder"
            else:
                state = "available"
        result: Work = {
            "account_id": account_id,
            "work_id": work_id,
            "state": state,
            "revision": copy.deepcopy(active_revision) if active_revision is not None else None,
            "heads": copy.deepcopy(heads),
            "missing": missing,
        }
        if sync_conflicts:
            result["sync_conflicts"] = sync_conflicts
        return result, parsed, complete

    @staticmethod
    def _empty_work(account_id: str, work_id: str) -> Work:
        return {
            "account_id": account_id,
            "work_id": work_id,
            "state": "placeholder",
            "revision": None,
            "heads": [],
            "missing": [],
        }

    def _validate_graph(self, parsed: Mapping[str, Revision]) -> None:
        visiting = set()
        visited = set()

        def visit(revision_id: str) -> None:
            if revision_id in visiting:
                raise LibraryValidationError("revision graph contains a loop")
            if revision_id in visited:
                return
            visiting.add(revision_id)
            revision = parsed[revision_id]
            for parent in revision["parents"]:
                if parent in parsed:
                    visit(parent)
            visiting.remove(revision_id)
            visited.add(revision_id)

        for revision_id in parsed:
            visit(revision_id)

    def _revision_complete(
        self,
        revision_id: str,
        parsed: Mapping[str, Revision],
        complete: Dict[str, Tuple[bool, Tuple[str, ...]]],
        visiting: set,
    ) -> Tuple[bool, Tuple[str, ...]]:
        if revision_id in complete:
            return complete[revision_id]
        if revision_id in visiting:
            raise LibraryValidationError("revision graph contains a loop")
        revision = parsed[revision_id]
        visiting.add(revision_id)
        missing: List[str] = []
        valid = True
        for parent in revision["parents"]:
            if parent not in parsed:
                valid = False
                missing.append(parent)
                continue
            parent_valid, parent_missing = self._revision_complete(parent, parsed, complete, visiting)
            if not parent_valid:
                valid = False
                missing.extend(parent_missing)
        for resource in revision["files"].values():
            object_status = self._object_status(resource["sha256"], resource["size"])
            if object_status == "missing":
                valid = False
                missing.append(resource["sha256"])
        visiting.remove(revision_id)
        result = (valid, tuple(sorted(set(missing))))
        complete[revision_id] = result
        return result

    def _load_revision(
        self, path: Path, account_id: str, work_id: str, revision_id: str
    ) -> Revision:
        document = self._read_json(path, str(path.relative_to(self._root)))
        if not isinstance(document, dict):
            raise LibraryValidationError("revision manifest must be an object")
        allowed = {
            "schema_version",
            "revision_id",
            "account_id",
            "work_id",
            "metadata",
            "files",
            "parents",
            "deleted",
        }
        if set(document) - allowed:
            raise LibraryValidationError("unknown revision manifest fields")
        if document.get("schema_version") != self.SCHEMA_VERSION:
            raise LibraryValidationError("unknown revision schema version")
        if document.get("revision_id") != revision_id:
            raise LibraryValidationError("revision filename does not match revision_id")
        self._safe_id(document.get("revision_id"), "revision_id")
        if document.get("account_id") != account_id or document.get("work_id") != work_id:
            raise LibraryValidationError("revision identity does not match its path")
        self._safe_id(document.get("account_id"), "account_id")
        self._safe_id(document.get("work_id"), "work_id")
        metadata = self._validate_metadata(document.get("metadata"))
        files = self._validate_files(document.get("files"))
        parents = document.get("parents")
        if not isinstance(parents, list):
            raise LibraryValidationError("parents must be a list")
        normalized_parents = []
        for parent in parents:
            parent_id = self._safe_id(parent, "parent revision id")
            if parent_id == revision_id or parent_id in normalized_parents:
                raise LibraryValidationError("invalid duplicate or self parent")
            normalized_parents.append(parent_id)
        deleted = document.get("deleted")
        if not isinstance(deleted, bool):
            raise LibraryValidationError("deleted must be a boolean")
        return {
            "schema_version": self.SCHEMA_VERSION,
            "revision_id": revision_id,
            "account_id": account_id,
            "work_id": work_id,
            "metadata": metadata,
            "files": files,
            "parents": normalized_parents,
            "deleted": deleted,
        }

    @staticmethod
    def _validate_metadata(metadata: Any) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            raise LibraryValidationError("metadata must be an object")
        try:
            result = copy.deepcopy(metadata)
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise LibraryValidationError("metadata must be JSON-serializable") from exc
        if "kind" not in result:
            result["kind"] = "episode"
        if not isinstance(result["kind"], str) or not result["kind"]:
            raise LibraryValidationError("metadata.kind must be a non-empty string")
        try:
            validate_episode_metadata_paths(result)
            validate_settings_metadata_paths(result)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc
        return result

    @staticmethod
    def _validate_files(files: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(files, dict):
            raise LibraryValidationError("files must be an object")
        try:
            paths = [validate_logical_path(path) for path in files]
            validate_case_unique(paths)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc
        normalized: Dict[str, Dict[str, Any]] = {}
        for path, resource in files.items():
            if not isinstance(path, str):
                raise LibraryValidationError("file paths must be strings")
            try:
                canonical = validate_logical_path(path)
            except ValueError as exc:
                raise LibraryValidationError(str(exc)) from exc
            if canonical != path:
                raise LibraryValidationError("file path is not canonical")
            if not isinstance(resource, dict):
                raise LibraryValidationError("file resource must be an object")
            if set(resource) != {"sha256", "size"}:
                raise LibraryValidationError("file resource has unknown fields")
            try:
                digest = validate_hash(resource["sha256"])
            except ValueError as exc:
                raise LibraryValidationError(str(exc)) from exc
            size = resource["size"]
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise LibraryValidationError("file resource size must be a non-negative integer")
            normalized[path] = {"sha256": digest, "size": size}
        return normalized

    def _require_object(self, digest: str, size: int) -> None:
        status = self._object_status(digest, size)
        if status == "missing":
            raise LibraryValidationError(f"missing object: {digest}")

    def _object_status(self, digest: str, size: int) -> str:
        path = self._object_path(digest)
        self._ensure_object_directories(digest)
        if path.is_symlink():
            raise LibraryValidationError(f"object is not a regular file: {digest}")
        if not path.exists():
            return "missing"
        if path.is_symlink() or not path.is_file():
            raise LibraryValidationError(f"object is not a regular file: {digest}")
        stat = path.stat()
        resolved_path = path.resolve()
        cache_key = (
            resolved_path,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            int(getattr(stat, "st_dev", 0)),
            int(getattr(stat, "st_ino", 0)),
        )
        if self._verified_objects.get(digest) == cache_key and stat.st_size == size:
            return "complete"
        actual_hash, actual_size = hash_file(path)
        if actual_hash != digest or actual_size != size:
            raise LibraryIntegrityError(f"corrupt object: {digest}")
        self._verified_objects[digest] = cache_key
        return "complete"

    # ------------------------------------------------------------------
    # Immutable merge helpers
    # ------------------------------------------------------------------
    def _iter_object_paths(self, conflicts: List[str]) -> Iterable[Path]:
        objects = self._root / "objects"
        if not objects.exists():
            return []
        self._reject_symlink(objects, "objects directory")
        paths: List[Path] = []
        for prefix_dir in sorted(objects.iterdir(), key=lambda item: item.name):
            relative = str(prefix_dir.relative_to(self._root))
            if is_sync_conflict_name(prefix_dir.name):
                conflicts.append(relative)
                continue
            if is_sync_temporary_name(prefix_dir.name):
                continue
            if prefix_dir.is_symlink() or not prefix_dir.is_dir():
                raise LibraryValidationError(f"invalid object prefix: {relative}")
            if len(prefix_dir.name) != 2 or any(char not in "0123456789abcdef" for char in prefix_dir.name):
                raise LibraryValidationError(f"invalid object prefix: {relative}")
            for entry in sorted(prefix_dir.iterdir(), key=lambda item: item.name):
                entry_relative = str(entry.relative_to(self._root))
                if is_sync_conflict_name(entry.name):
                    conflicts.append(entry_relative)
                    continue
                if is_sync_temporary_name(entry.name):
                    continue
                if entry.is_symlink() or not entry.is_file():
                    raise LibraryValidationError(f"invalid object: {entry_relative}")
                try:
                    digest = validate_hash(entry.name)
                except ValueError as exc:
                    raise LibraryValidationError(str(exc)) from exc
                if digest[:2] != prefix_dir.name:
                    raise LibraryValidationError(f"object prefix does not match hash: {entry_relative}")
                actual_hash, _size = hash_file(entry)
                if actual_hash != digest:
                    raise LibraryIntegrityError(f"corrupt object: {digest}")
                paths.append(entry)
        return paths

    def _iter_manifest_paths(
        self, conflicts: List[str]
    ) -> Iterable[Tuple[Path, str, str, str]]:
        accounts = self._root / "accounts"
        if not accounts.exists():
            return []
        self._reject_symlink(accounts, "accounts directory")
        result: List[Tuple[Path, str, str, str]] = []
        account_names: List[str] = []
        for account_dir in sorted(accounts.iterdir(), key=lambda item: item.name):
            relative = str(account_dir.relative_to(self._root))
            if is_sync_conflict_name(account_dir.name):
                conflicts.append(relative)
                continue
            if is_sync_temporary_name(account_dir.name):
                continue
            if account_dir.is_symlink() or not account_dir.is_dir():
                raise LibraryValidationError(f"invalid account directory: {relative}")
            account_id = self._safe_id(account_dir.name, "account_id")
            account_names.append(account_id)
            works_dir = account_dir / "works"
            if not works_dir.exists():
                continue
            self._reject_symlink(works_dir, "works directory")
            work_names: List[str] = []
            for work_dir in sorted(works_dir.iterdir(), key=lambda item: item.name):
                work_relative = str(work_dir.relative_to(self._root))
                if is_sync_conflict_name(work_dir.name):
                    conflicts.append(work_relative)
                    continue
                if is_sync_temporary_name(work_dir.name):
                    continue
                if work_dir.is_symlink() or not work_dir.is_dir():
                    raise LibraryValidationError(f"invalid work directory: {work_relative}")
                work_id = self._safe_id(work_dir.name, "work_id")
                work_names.append(work_id)
                revisions_dir = work_dir / "revisions"
                if not revisions_dir.exists():
                    continue
                self._reject_symlink(revisions_dir, "revisions directory")
                revision_names: List[str] = []
                for entry in sorted(revisions_dir.iterdir(), key=lambda item: item.name):
                    entry_relative = str(entry.relative_to(self._root))
                    if is_sync_conflict_name(entry.name):
                        conflicts.append(entry_relative)
                        continue
                    if is_sync_temporary_name(entry.name):
                        continue
                    if entry.is_symlink() or entry.is_dir():
                        raise LibraryValidationError(f"invalid revision entry: {entry_relative}")
                    if entry.suffix != ".json":
                        continue
                    revision_id = entry.stem
                    self._safe_id(revision_id, "revision_id")
                    revision_names.append(revision_id)
                    result.append((entry, account_id, work_id, revision_id))
                self._ensure_case_unique(revision_names, "revision ids")
            self._ensure_case_unique(work_names, "work ids")
        self._ensure_case_unique(account_names, "account ids")
        return result

    def _copy_object_immutable(self, source: Path, destination: Path) -> bool:
        digest = source.name
        source_hash, source_size = hash_file(source)
        if source_hash != digest:
            raise LibraryIntegrityError(f"corrupt source object: {digest}")
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise LibraryCollisionError(f"object collision: {digest}")
            target_hash, target_size = hash_file(destination)
            if target_hash != digest or target_size != source_size:
                raise LibraryCollisionError(f"object collision: {digest}")
            return False
        self._ensure_existing_parent_chain(destination.parent, self._root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return True

    def _copy_manifest_immutable(self, source: Path, destination: Path) -> bool:
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise LibraryCollisionError(f"manifest collision: {destination}")
            source_document = self._read_json(source, "source manifest")
            target_document = self._read_json(destination, "target manifest")
            if self._canonical_json(source_document) != self._canonical_json(target_document):
                raise LibraryCollisionError(f"manifest collision: {destination}")
            return False
        self._ensure_existing_parent_chain(destination.parent, self._root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, source.read_bytes())
        return True

    # ------------------------------------------------------------------
    # Filesystem/path helpers
    # ------------------------------------------------------------------
    def _ensure_directory_layout(self) -> None:
        for relative in ("objects", "accounts"):
            directory = self._root / relative
            if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
                raise LibraryValidationError(f"library entry is not a directory: {relative}")
            directory.mkdir(parents=True, exist_ok=True)

    def _object_path(self, digest: str) -> Path:
        try:
            digest = validate_hash(digest)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc
        return self._root / "objects" / digest[:2] / digest

    def _revision_dir(self, account_id: str, work_id: str) -> Path:
        return self._root / "accounts" / account_id / "works" / work_id / "revisions"

    def _revision_path(self, account_id: str, work_id: str, revision_id: str) -> Path:
        self._safe_id(revision_id, "revision_id")
        return self._revision_dir(account_id, work_id) / f"{revision_id}.json"

    @staticmethod
    def _safe_id(value: object, field: str) -> str:
        try:
            return validate_identifier(value, field)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc

    @staticmethod
    def _ensure_case_unique(values: Iterable[str], description: str) -> None:
        try:
            validate_case_unique(values)
        except ValueError as exc:
            raise LibraryValidationError(f"case-colliding {description}") from exc

    @staticmethod
    def _reject_symlink(path: Path, description: str) -> None:
        if path.is_symlink():
            raise LibraryValidationError(f"{description} must not be a symlink")

    def _ensure_work_path_components(self, account_id: str, work_id: str) -> None:
        components = (
            (self._root / "accounts", "accounts directory"),
            (self._root / "accounts" / account_id, "account directory"),
            (self._root / "accounts" / account_id / "works", "works directory"),
            (
                self._root / "accounts" / account_id / "works" / work_id,
                "work directory",
            ),
            (self._revision_dir(account_id, work_id), "revisions directory"),
        )
        for path, description in components:
            if path.is_symlink():
                raise LibraryValidationError(f"{description} must not be a symlink")
            if path.exists() and not path.is_dir():
                raise LibraryValidationError(f"{description} must be a directory")

    def _ensure_revision_directories(self, account_id: str, work_id: str) -> None:
        self._ensure_work_path_components(account_id, work_id)

    def _ensure_object_directories(self, digest: str) -> None:
        objects = self._root / "objects"
        prefix = objects / digest[:2]
        for path, description in ((objects, "objects directory"), (prefix, "object prefix")):
            if path.is_symlink():
                raise LibraryValidationError(f"{description} must not be a symlink")
            if path.exists() and not path.is_dir():
                raise LibraryValidationError(f"{description} must be a directory")

    @staticmethod
    def _ensure_existing_parent_chain(path: Path, root: Path) -> None:
        """Reject symlink/file ancestors before creating a destination."""

        path = Path(path)
        root = Path(root)
        current = path
        while True:
            if current.exists():
                if current.is_symlink():
                    raise LibraryValidationError("destination path contains a symlink")
                if not current.is_dir():
                    raise LibraryValidationError("destination parent is not a directory")
            if current == root or current.parent == current:
                return
            current = current.parent

    @staticmethod
    def _read_json(path: Path, description: str) -> Any:
        try:
            if path.is_symlink() or not path.is_file():
                raise LibraryValidationError(f"{description} is not a regular file")
            with path.open("r", encoding="utf-8") as stream:
                return json.load(stream)
        except LibraryValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LibraryValidationError(f"invalid {description}") from exc

    @classmethod
    def _validate_library_document(cls, document: Any) -> str:
        if not isinstance(document, dict):
            raise LibraryValidationError("library.json must be an object")
        allowed = {"format", "schema_version", "library_id"}
        if set(document) - allowed:
            raise LibraryValidationError("unknown library.json fields")
        if document.get("schema_version") != cls.SCHEMA_VERSION:
            raise LibraryValidationError("unknown library schema version")
        if document.get("format", cls.FORMAT) != cls.FORMAT:
            raise LibraryValidationError("unknown library format")
        try:
            return validate_identifier(document.get("library_id"), "library_id")
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc

    @staticmethod
    def _canonical_json(document: Any) -> bytes:
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _json_bytes(cls, document: Any) -> bytes:
        return cls._canonical_json(document) + b"\n"

    @staticmethod
    def _object_status_for_copy(path: Path) -> Tuple[str, int]:
        try:
            return hash_file(path)
        except ValueError as exc:
            raise LibraryValidationError(str(exc)) from exc

    @staticmethod
    def _prepare_materialize_target(output: Path) -> None:
        ResourceLibrary._ensure_existing_parent_chain(output.parent, Path(output.anchor or "/"))
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_dir():
                raise LibraryValidationError("materialize target must be a dedicated directory")
            try:
                next(output.iterdir())
            except StopIteration:
                return
            raise LibraryValidationError("materialize target must be empty")
        output.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_materialized_destination(root: Path, logical_path: str) -> Path:
        destination = root.joinpath(*logical_path.split("/"))
        root_resolved = root.resolve()
        destination_parent = destination.parent.resolve(strict=False)
        try:
            destination_parent.relative_to(root_resolved)
        except ValueError as exc:
            raise LibraryValidationError("logical path escapes materialize target") from exc
        return destination

    @staticmethod
    def _reject_path_symlinks(root: Path, path: Path) -> None:
        current = path
        root = root.resolve()
        while True:
            if current.is_symlink():
                raise LibraryValidationError("materialize target contains a symlink")
            if current == root:
                return
            if current.parent == current:
                raise LibraryValidationError("materialize target escaped root")
            current = current.parent

    def _copy_verified_object(self, digest: str, size: int, destination: Path) -> None:
        source = self._object_path(digest)
        self._require_object(digest, size)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._reject_path_symlinks(destination.parent.parent if destination.parent.parent else destination.parent, destination.parent)
        temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            # The caller has checked that the destination is fresh.  Replace
            # only the temporary name; the final path cannot clobber content.
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
