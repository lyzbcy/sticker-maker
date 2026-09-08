"""Account-scoped shared settings and resource configuration.

Settings are stored as ordinary immutable catalog works with
``metadata.kind == 'settings'``.  The adapter deliberately keeps the local
materialized configuration separate from the shared catalog so a computer can
retain device-only preferences and uncommitted edits while another computer
continues to receive shared series, prompts, bases, and references.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - the engine already depends on PyYAML
    yaml = None

from .catalog import (
    LibraryIntegrityError,
    LibraryStateError,
    LibraryValidationError,
    ResourceLibrary,
)


PREF_KEYS = {
    "mode_probs",
    "single_char_probs",
    "base_probs",
    "grid_size",
    "transparent_default",
    "ref_lib_priority",
    "ref_consume",
    "story_mode",
    "reference_lib_path",
    "default_series_id",
    "prompt_set_id",
    "vision_calls",
    "sticker_price",
    "price_probs",
}
PRIVATE_NAMES = {
    ".env",
    ".stfolder",
    ".stignore",
    ".stversions",
    "auth.json",
    "cookies",
    ".browser-data",
    "publish_credentials.json",
    "publish_storage.json",
    "device.json",
}
SERIES_KEYS = {
    "id",
    "name",
    "start_number",
    "next_number",
    "intro_prompt",
    "role_asset_map",
}
PROMPT_KEYS = {
    "id",
    "name",
    "style_block",
    "combo_extra",
    "story_extra",
    "ref_extra",
    "updated_at",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOMBSTONE_SETTING_TYPES = frozenset({"prompt", "base", "series"})


def settings_dir(runtime: Any) -> Path:
    """Return the per-library, per-account local settings directory."""

    account_id = str(getattr(runtime, "account_id", "") or "")
    if not account_id or not _ID_RE.fullmatch(account_id):
        raise ValueError("请先绑定有效的平台账号")
    state = getattr(runtime, "state", {}) or {}
    library_id = str(state.get("library_id") or "")
    if not library_id:
        library = getattr(runtime, "library", None)
        library_id = str(getattr(library, "library_id", "") or "")
    if not library_id or not _ID_RE.fullmatch(library_id):
        raise ValueError("资源库身份无效")
    workspace_base = getattr(runtime, "workspace_base", None)
    if workspace_base is None:
        local = Path(getattr(runtime, "local", Path(getattr(runtime, "user_data")) / "resource_library"))
        workspace_base = local / "workspaces"
    return (Path(workspace_base) / library_id / account_id / "settings").resolve()


class SharedSettings:
    """Capture and apply the settings owned by the active runtime account."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.library: ResourceLibrary = runtime.library
        self.root = settings_dir(runtime)
        self.account_id = str(runtime.account_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def seed_legacy(self) -> Dict[str, Any]:
        """Copy legacy user settings into the account workspace once.

        Existing local settings win so a second bind or a repeated startup
        cannot silently overwrite a user's edits.  Legacy source files stay
        where they are; the caller can capture the resulting workspace after
        binding.
        """

        self._require_account()
        self.root.mkdir(parents=True, exist_ok=True)
        source_root = Path(self.runtime.user_data)
        seeded = 0
        skipped = 0
        missing: List[str] = []

        source_prefs = source_root / "prefs.yaml"
        legacy_prefs = self._load_yaml(source_prefs) if source_prefs.is_file() else {}
        destination_prefs = self.root / "prefs.yaml"
        if source_prefs.is_file():
            if destination_prefs.exists():
                skipped += 1
            else:
                payload = self._sanitize_prefs(legacy_prefs)
                self._write_yaml(destination_prefs, payload)
                seeded += 1

        for relative in ("series.json",):
            source = source_root / relative
            destination = self.root / relative
            if not source.is_file() or self._is_private(source):
                continue
            if destination.exists():
                skipped += 1
            else:
                self._copy_file(source, destination)
                seeded += 1

        # Normalize copied series asset references inside the account
        # workspace.  The legacy series file itself remains untouched.
        series_missing = self._normalize_local_series_file()
        missing.extend(series_missing)

        for relative_root in ("prompts", "custom_bases", "reference_library"):
            source = source_root / relative_root
            if source.is_dir():
                count, ignored = self._copy_tree_if_missing(source, self.root / relative_root)
                seeded += count
                skipped += ignored

        external_reference = legacy_prefs.get("reference_lib_path") if isinstance(legacy_prefs, dict) else None
        if external_reference:
            external = Path(str(external_reference)).expanduser()
            if not external.is_absolute():
                external = source_root / external
            external = external.resolve()
            if external.is_dir() and external != (source_root / "reference_library").resolve():
                count, ignored = self._copy_tree_if_missing(
                    external, self.root / "reference_library"
                )
                seeded += count
                skipped += ignored
            elif not external.exists():
                missing.append(str(external_reference))

        return {"seeded": seeded, "skipped": skipped, "missing": missing, "settings_dir": str(self.root)}

    def capture(self) -> Dict[str, Any]:
        """Version local setting entities that changed since their marker."""

        self._require_account()
        self.root.mkdir(parents=True, exist_ok=True)
        entities, collection_missing, used_hashes = self._collect_entities()
        markers = self._markers()
        conflicts: List[str] = []
        missing: List[Any] = list(collection_missing)
        captured = 0
        unchanged = 0
        deferred = 0
        tombstones: List[str] = []

        for entity in entities:
            entity_id = entity["work_id"]
            fingerprint = self._fingerprint(entity["metadata"], entity["files"])
            marker = self._marker_for(markers, entity_id)
            work = self.library.read_work(self.account_id, entity_id)
            active = work.get("revision")
            branch_conflict = False

            if work.get("state") == "pending":
                missing.append({"work_id": entity_id, "missing": work.get("missing", [])})
                continue
            if work.get("state") == "conflict":
                conflicts.append(entity_id)
                continue
            marker_revision = marker.get("revision_id") if marker else None
            if marker_revision and active and active.get("revision_id") != marker_revision:
                # A peer advanced the entity.  A local change would create an
                # explicit local branch from the true marker parent.  The
                # catalog then exposes both heads to the conflict UI instead
                # of silently dropping the local edit.
                if marker.get("fingerprint") != fingerprint:
                    branch_conflict = True
                else:
                    deferred += 1
                    continue
            if marker and marker.get("fingerprint") == fingerprint and marker.get("revision_id"):
                unchanged += 1
                continue

            if marker_revision and not active and work.get("heads"):
                conflicts.append(entity_id)
                continue

            if not marker_revision and active:
                # A newly connected computer may already have the exact
                # shared entity in its legacy workspace.  Adopt that head
                # instead of manufacturing a no-op branch.
                active_fingerprint = self._fingerprint(
                    active.get("metadata", {}), active.get("files", {})
                )
                if active_fingerprint == fingerprint:
                    markers[entity_id] = self._new_marker(active["revision_id"], fingerprint, entity)
                    unchanged += 1
                    continue

            parents: Optional[Sequence[str]]
            if marker_revision:
                parents = [marker_revision]
            else:
                # A local workspace with no marker is independent from the
                # existing shared head.  Starting with no parent creates a
                # visible branch; adopting all heads here would manufacture a
                # silent merge and overwrite a peer's settings.
                parents = []
            try:
                revision = self.library.write_revision(
                    self.account_id,
                    entity_id,
                    entity["metadata"],
                    entity["files"],
                    parents=parents,
                )
            except (LibraryValidationError, LibraryIntegrityError) as exc:
                missing.append({"work_id": entity_id, "error": str(exc)})
                continue
            markers[entity_id] = self._new_marker(revision["revision_id"], fingerprint, entity)
            captured += 1
            if branch_conflict:
                conflicts.append(entity_id)

        # A missing prompt/base/series entity is an explicit local deletion
        # only when this device has a marker for it.  References intentionally
        # remain union-like: removing a local reference copy must not remove
        # the shared reference from another device.
        present_ids = {entity["work_id"] for entity in entities}
        for entity_id, marker_value in list(markers.items()):
            if entity_id in present_ids:
                continue
            marker = self._marker_for(markers, entity_id)
            setting_type = marker.get("setting_type")
            if setting_type not in _TOMBSTONE_SETTING_TYPES:
                continue
            work = self.library.read_work(self.account_id, entity_id)
            if work.get("state") == "deleted":
                unchanged += 1
                continue
            if work.get("state") == "pending":
                missing.append({"work_id": entity_id, "missing": work.get("missing", [])})
                continue
            if work.get("state") == "conflict":
                conflicts.append(entity_id)
                continue
            active = work.get("revision")
            marker_revision = marker.get("revision_id")
            if not active or not marker_revision:
                continue
            if active.get("revision_id") != marker_revision:
                # A peer changed the entity after this device's last marker;
                # the local disappearance must be reviewed as a conflict.
                conflicts.append(entity_id)
                continue
            metadata = copy.deepcopy(active.get("metadata") or {})
            files = copy.deepcopy(active.get("files") or {})
            entity = {
                "work_id": entity_id,
                "metadata": metadata,
                "files": files,
                "logical_path": marker.get("logical_path") or metadata.get("logical_path"),
            }
            try:
                revision = self.library.write_revision(
                    self.account_id,
                    entity_id,
                    metadata,
                    files,
                    parents=[marker_revision],
                    deleted=True,
                )
            except (LibraryValidationError, LibraryIntegrityError) as exc:
                missing.append({"work_id": entity_id, "error": str(exc)})
                continue
            markers[entity_id] = self._new_marker(
                revision["revision_id"], self._fingerprint(metadata, files), entity
            )
            captured += 1
            tombstones.append(entity_id)

        self._merge_used_reference_state(used_hashes)
        self._save_state()
        return {
            "captured": captured,
            "unchanged": unchanged,
            "deferred": deferred,
            "conflicts": conflicts,
            "missing": missing,
            "tombstones": tombstones,
            "settings_dir": str(self.root),
        }

    def apply(self) -> Dict[str, Any]:
        """Apply complete, non-conflicting shared settings to local files."""

        self._require_account()
        self.root.mkdir(parents=True, exist_ok=True)
        entities, local_missing, _used = self._collect_entities()
        local_by_id = {
            entity["work_id"]: self._fingerprint(entity["metadata"], entity["files"])
            for entity in entities
        }
        markers = self._markers()
        conflicts: List[str] = []
        missing: List[Any] = list(local_missing)
        remote_used_hashes: set = set()
        staged: List[Tuple[Dict[str, Any], Path, str]] = []
        tombstone_candidates: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
        remote_series_payloads: List[Dict[str, Any]] = []
        unchanged = 0
        applied = 0
        series_blocked = False
        try:
            for work in self.library.list_works(self.account_id):
                revision = work.get("revision")
                heads = work.get("heads") or []
                candidate = revision or (heads[0] if heads else None)
                if not candidate or candidate.get("metadata", {}).get("kind") != "settings":
                    continue
                entity_id = work["work_id"]
                marker = self._marker_for(markers, entity_id)
                setting_type = candidate.get("metadata", {}).get("setting_type")
                setting_payload = candidate.get("metadata", {}).get("payload", {})
                if work.get("state") == "conflict":
                    if candidate.get("metadata", {}).get("setting_type") == "series":
                        series_blocked = True
                    conflicts.append(entity_id)
                    continue
                if work.get("state") == "pending":
                    if candidate.get("metadata", {}).get("setting_type") == "series":
                        series_blocked = True
                    missing.append({"work_id": entity_id, "missing": work.get("missing", [])})
                    continue
                if work.get("state") == "deleted":
                    # Deleted settings entities carry their previous metadata
                    # and files so the local fingerprint can detect edits
                    # made before applying the tombstone.  References use
                    # union semantics and are deliberately not removed.
                    if setting_type not in _TOMBSTONE_SETTING_TYPES:
                        continue
                    revision_fingerprint = self._fingerprint(
                        candidate["metadata"], candidate["files"]
                    )
                    local_fingerprint = local_by_id.get(entity_id)
                    marker_fingerprint = marker.get("fingerprint") if marker else None
                    if marker and marker.get("revision_id") == candidate["revision_id"]:
                        if marker_fingerprint is None or local_fingerprint is None or local_fingerprint == marker_fingerprint:
                            unchanged += 1
                            continue
                        if setting_type == "series":
                            series_blocked = True
                        conflicts.append(entity_id)
                        continue
                    if marker and marker_fingerprint and local_fingerprint not in (None, marker_fingerprint):
                        if setting_type == "series":
                            series_blocked = True
                        conflicts.append(entity_id)
                        continue
                    if not marker and local_fingerprint is not None and local_fingerprint != revision_fingerprint:
                        if setting_type == "series":
                            series_blocked = True
                        conflicts.append(entity_id)
                        continue
                    tombstone_candidates.append((work, candidate, revision_fingerprint))
                    continue

                if setting_type == "series":
                    payload = candidate.get("metadata", {}).get("payload", {})
                    if isinstance(payload, dict):
                        remote_series_payloads.append(self._apply_series_payload(payload))
                if setting_type == "reference":
                    digest = setting_payload.get("sha256") if isinstance(setting_payload, dict) else None
                    used = bool(setting_payload.get("used")) if isinstance(setting_payload, dict) else False
                    logical = str(setting_payload.get("logical_path", "")) if isinstance(setting_payload, dict) else ""
                    if used or any(part.startswith("_used_") or part == "_used_shared" for part in Path(logical).parts):
                        if digest:
                            remote_used_hashes.add(str(digest))
                    elif digest in self._known_used_hashes():
                        # A stale available branch must not resurrect a
                        # reference that this account has already consumed.
                        continue

                revision_fingerprint = self._fingerprint(
                    candidate["metadata"], candidate["files"]
                )
                local_fingerprint = local_by_id.get(entity_id)
                marker_fingerprint = marker.get("fingerprint") if marker else None
                if marker and marker.get("revision_id") == candidate["revision_id"]:
                    if local_fingerprint is None:
                        # 本地实体尚未物化（迁移切换库/新设备的工作缓存为空）：
                        # 落入下方 stage 将库版本写出到本地，而非误判为本地修改冲突
                        pass
                    elif marker_fingerprint is None or local_fingerprint == marker_fingerprint:
                        unchanged += 1
                        continue
                    else:
                        if candidate.get("metadata", {}).get("setting_type") == "series":
                            series_blocked = True
                        conflicts.append(entity_id)
                        continue
                if marker and marker_fingerprint and local_fingerprint not in (None, marker_fingerprint):
                    if candidate.get("metadata", {}).get("setting_type") == "series":
                        series_blocked = True
                    conflicts.append(entity_id)
                    continue
                if not marker and local_fingerprint is not None and local_fingerprint != revision_fingerprint:
                    if candidate.get("metadata", {}).get("setting_type") == "series":
                        series_blocked = True
                    conflicts.append(entity_id)
                    continue

                stage = Path(tempfile.mkdtemp(prefix=".settings-", dir=str(self.root.parent)))
                try:
                    self.library.materialize(
                        self.account_id, entity_id, stage, candidate["revision_id"]
                    )
                except (LibraryStateError, LibraryValidationError, LibraryIntegrityError) as exc:
                    shutil.rmtree(stage, ignore_errors=True)
                    missing.append({"work_id": entity_id, "error": str(exc)})
                    continue
                staged.append((work, stage, revision_fingerprint))

            # A series file is an aggregate of independent series entities;
            # only replace it if every changed series entity is safe to apply.
            series_items: List[Dict[str, Any]] = []
            series_staged = []
            for work, stage, fp in staged:
                metadata = work["revision"]["metadata"]
                if metadata.get("setting_type") == "series":
                    series_staged.append((work, stage, fp))
            if series_staged and not series_blocked:
                series_items.extend(remote_series_payloads)
                series_items.sort(key=lambda item: str(item.get("id", "")))
                self._write_json(self.root / "series.json", series_items)

            safe_tombstones = [item for item in tombstone_candidates
                               if (item[1].get("metadata", {}).get("setting_type") != "series"
                                   or not series_blocked)]
            series_deleted = []
            if safe_tombstones and not series_staged and not series_blocked:
                series_deleted = [
                    str(item[1].get("metadata", {}).get("payload", {}).get("id"))
                    for item in safe_tombstones
                    if item[1].get("metadata", {}).get("setting_type") == "series"
                    and item[1].get("metadata", {}).get("payload", {}).get("id")
                ]
                if series_deleted:
                    self._remove_series_entities(series_deleted, missing)

            for work, candidate, fp in safe_tombstones:
                metadata = candidate.get("metadata", {})
                setting_type = metadata.get("setting_type")
                if setting_type == "series":
                    # The aggregate series file was handled above.  When an
                    # active series batch is also staged, its complete remote
                    # list already omits this tombstoned entity.
                    pass
                else:
                    self._remove_deleted_entity(metadata, missing)
                markers[work["work_id"]] = self._new_marker(
                    candidate["revision_id"], fp, {
                        "work_id": work["work_id"],
                        "metadata": metadata,
                        "files": candidate.get("files") or {},
                        "logical_path": metadata.get("logical_path"),
                    }
                )
                applied += 1

            for work, stage, fp in staged:
                metadata = work["revision"]["metadata"]
                setting_type = metadata.get("setting_type")
                if setting_type == "series":
                    # The aggregate write above handled this entity.
                    if series_blocked:
                        continue
                elif setting_type == "prefs":
                    payload = self._apply_prefs_payload(metadata.get("payload", {}))
                    if payload.get("reference_lib_path"):
                        payload["reference_lib_path"] = str(self.root / "reference_library")
                    self._write_yaml(self.root / "prefs.yaml", payload)
                else:
                    self._apply_entity_files(stage, metadata)
                markers[work["work_id"]] = self._new_marker(
                    work["revision"]["revision_id"], fp, {
                        "work_id": work["work_id"],
                        "metadata": metadata,
                        "files": work["revision"]["files"],
                    }
                )
                applied += 1
        finally:
            for _work, stage, _fp in staged:
                shutil.rmtree(stage, ignore_errors=True)

        self._merge_used_reference_state(remote_used_hashes)
        self._save_state()
        return {
            "applied": applied,
            "unchanged": unchanged,
            "conflicts": conflicts,
            "missing": missing,
            "tombstones": [work["work_id"] for work, _candidate, _fp in safe_tombstones],
            "settings_dir": str(self.root),
        }

    # ------------------------------------------------------------------
    # Entity collection
    # ------------------------------------------------------------------
    def _collect_entities(self) -> Tuple[List[Dict[str, Any]], List[Any], set]:
        entities: List[Dict[str, Any]] = []
        missing: List[Any] = []
        used_hashes: set = set()
        if not self.root.exists():
            return entities, missing, used_hashes

        prefs = self.root / "prefs.yaml"
        if prefs.is_file():
            try:
                payload = self._sanitize_prefs(self._load_yaml(prefs))
                resource = self._put_bytes(self._dump_yaml(payload), ".yaml")
                entities.append(self._entity(
                    "prefs",
                    "prefs",
                    "prefs.yaml",
                    {"kind": "settings", "setting_type": "prefs", "logical_path": "prefs.yaml", "payload": payload},
                    {"prefs.yaml": resource},
                ))
            except (OSError, ValueError, TypeError) as exc:
                missing.append({"logical_path": "prefs.yaml", "error": str(exc)})

        series_path = self.root / "series.json"
        if series_path.is_file():
            try:
                raw = json.loads(series_path.read_text(encoding="utf-8"))
                if not isinstance(raw, list):
                    raise ValueError("series.json must contain a list")
                seen_series = set()
                normalized_series = []
                for item in raw:
                    if not isinstance(item, dict) or not item.get("id"):
                        missing.append({"logical_path": "series.json", "error": "series entry lacks id"})
                        continue
                    item = self._sanitize_series(item)
                    series_id = str(item["id"])
                    if series_id in seen_series:
                        continue
                    seen_series.add(series_id)
                    payload, asset_files, asset_missing = self._normalize_series(item)
                    missing.extend(asset_missing)
                    normalized_series.append(payload)
                    for logical, source in asset_files.items():
                        self._ensure_local_asset(logical, source)
                    logical_entity_file = f"series/entity-{self._token(series_id)}.json"
                    files = {logical_entity_file: self._put_bytes(self._json_bytes(payload), ".json")}
                    for logical, source in asset_files.items():
                        files[logical] = self.library.put_file(source)
                    entities.append(self._entity(
                        "series",
                        series_id,
                        "series.json",
                        {"kind": "settings", "setting_type": "series", "logical_path": "series.json", "payload": payload},
                        files,
                    ))
                if normalized_series != raw:
                    self._write_json(series_path, normalized_series)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                missing.append({"logical_path": "series.json", "error": str(exc)})

        prompts = self.root / "prompts"
        if prompts.is_dir():
            for path in sorted(prompts.glob("*.json")):
                if path.is_symlink() or not path.is_file() or self._is_private(path):
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("prompt must be an object")
                    payload = self._sanitize_prompt(payload)
                    prompt_id = str(payload.get("id") or path.stem)
                    payload.setdefault("id", prompt_id)
                    logical = f"prompts/entity-{self._token(prompt_id)}.json"
                    entities.append(self._entity(
                        "prompt",
                        prompt_id,
                        f"prompts/{path.name}",
                        {"kind": "settings", "setting_type": "prompt", "logical_path": f"prompts/{path.name}", "payload": payload},
                        {logical: self._put_bytes(self._json_bytes(payload), ".json")},
                    ))
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    missing.append({"logical_path": str(path.relative_to(self.root)), "error": str(exc)})

        entities.extend(self._collect_files("base", self.root / "custom_bases", "custom_bases", missing))

        reference_root = self.root / "reference_library"
        reference_files = self._iter_files(reference_root)
        known_used = self._known_used_hashes()
        for path in reference_files:
            logical = path.relative_to(self.root).as_posix()
            resource = self.library.put_file(path)
            digest = resource["sha256"]
            is_used = any(part.startswith("_used_") or part == "_used_shared" for part in path.relative_to(reference_root).parts)
            if is_used:
                used_hashes.add(digest)
            elif digest in known_used:
                # A resource that was consumed elsewhere must not silently
                # become available again if a stale copy returns.
                continue
            entities.append(self._entity(
                "reference",
                digest,
                logical,
                {"kind": "settings", "setting_type": "reference", "logical_path": logical,
                 "payload": {"sha256": digest, "used": is_used, "logical_path": logical}},
                {logical: resource},
            ))
        return entities, missing, used_hashes

    def _collect_files(
        self, setting_type: str, root: Path, prefix: str, missing: List[Any]
    ) -> List[Dict[str, Any]]:
        result = []
        for path in self._iter_files(root):
            logical = path.relative_to(self.root).as_posix()
            try:
                resource = self.library.put_file(path)
            except (OSError, ValueError) as exc:
                missing.append({"logical_path": logical, "error": str(exc)})
                continue
            result.append(self._entity(
                setting_type,
                logical,
                logical,
                {"kind": "settings", "setting_type": setting_type, "logical_path": logical,
                 "payload": {"logical_path": logical}},
                {logical: resource},
            ))
        return result

    def _entity(
        self,
        setting_type: str,
        key: str,
        logical_path: str,
        metadata: Dict[str, Any],
        files: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "work_id": self._entity_id(setting_type, key),
            "metadata": metadata,
            "files": files,
            "logical_path": logical_path,
        }

    # ------------------------------------------------------------------
    # Series/assets and local application
    # ------------------------------------------------------------------
    def _normalize_series(self, value: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Path], List[Any]]:
        payload = copy.deepcopy(dict(value))
        assets: Dict[str, Path] = {}
        missing: List[Any] = []
        role_map = payload.get("role_asset_map")
        if not isinstance(role_map, dict):
            return payload, assets, missing
        for role, role_assets in list(role_map.items()):
            if not isinstance(role_assets, dict):
                continue
            for kind, raw in list(role_assets.items()):
                if not isinstance(raw, str) or not raw:
                    continue
                source = self._find_asset(raw)
                if source is None:
                    if Path(raw).is_absolute():
                        logical_missing = "_missing_assets/" + self._token(raw) + Path(raw).suffix.lower()
                        role_assets[kind] = logical_missing
                        missing.append({"logical_path": logical_missing, "source": raw})
                    continue
                if self._inside(source, self.root) and source.relative_to(self.root).as_posix().startswith("_assets/"):
                    logical = source.relative_to(self.root).as_posix()
                else:
                    digest, _size = self._hash_path(source)
                    logical = f"_assets/{digest}{source.suffix.lower()}"
                assets[logical] = source
                role_assets[kind] = logical
        return payload, assets, missing

    def _find_asset(self, raw: str) -> Optional[Path]:
        candidate = Path(raw).expanduser()
        options = []
        if candidate.is_absolute():
            options.append(candidate)
        else:
            options.extend((self.root / candidate, Path(self.runtime.user_data) / candidate))
        for option in options:
            if option.is_file() and not option.is_symlink():
                return option.resolve()
        return None

    def _normalize_local_series_file(self) -> List[Any]:
        series_path = self.root / "series.json"
        if not series_path.is_file():
            return []
        try:
            raw = json.loads(series_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return [{"logical_path": "series.json", "error": "series.json must contain a list"}]
            normalized = []
            missing: List[Any] = []
            for item in raw:
                if not isinstance(item, dict) or not item.get("id"):
                    missing.append({"logical_path": "series.json", "error": "series entry lacks id"})
                    continue
                payload, assets, asset_missing = self._normalize_series(item)
                normalized.append(payload)
                missing.extend(asset_missing)
                for logical, source in assets.items():
                    self._ensure_local_asset(logical, source)
            if normalized != raw:
                self._write_json(series_path, normalized)
            return missing
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return [{"logical_path": "series.json", "error": str(exc)}]

    def _ensure_local_asset(self, logical: str, source: Path) -> None:
        target = self.root / logical
        if target.exists():
            source_hash, source_size = self._hash_path(source)
            target_hash, target_size = self._hash_path(target)
            if source_hash != target_hash or source_size != target_size:
                raise LibraryIntegrityError(f"local asset collision: {logical}")
            return
        self._copy_file(source, target)

    def _apply_entity_files(self, stage: Path, metadata: Mapping[str, Any]) -> None:
        setting_type = metadata.get("setting_type")
        logical_path = metadata.get("logical_path")
        if setting_type == "prompt":
            payload = metadata.get("payload", {})
            prompt_id = str(payload.get("id") or Path(str(logical_path)).stem)
            filename = prompt_id if _ID_RE.fullmatch(prompt_id) else f"entity-{self._token(prompt_id)}"
            target = self.root / "prompts" / f"{filename}.json"
            self._write_json(target, payload)
            return
        if setting_type == "base":
            self._copy_stage_files(stage, self.root)
            return
        if setting_type == "reference":
            self._copy_stage_files(stage, self.root)

    @staticmethod
    def _sanitize_series(value: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            key: copy.deepcopy(value[key])
            for key in SERIES_KEYS
            if key in value
        }

    @staticmethod
    def _sanitize_prompt(value: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            key: copy.deepcopy(value[key])
            for key in PROMPT_KEYS
            if key in value
        }

    def _apply_series_payload(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(dict(payload))
        role_map = result.get("role_asset_map")
        if isinstance(role_map, dict):
            for role_assets in role_map.values():
                if not isinstance(role_assets, dict):
                    continue
                for kind, raw in list(role_assets.items()):
                    if isinstance(raw, str) and raw.startswith("_assets/"):
                        role_assets[kind] = str(self.root / raw)
                    elif isinstance(raw, str) and raw.startswith("_missing_assets/"):
                        role_assets[kind] = str(self.root / raw)
        return result

    def _copy_stage_files(self, stage: Path, destination_root: Path) -> None:
        for source in self._iter_files(stage):
            logical = source.relative_to(stage).as_posix()
            target = destination_root / logical
            self._copy_file(source, target)

    def _remove_deleted_entity(self, metadata: Mapping[str, Any], missing: List[Any]) -> None:
        """Remove one safely-scoped prompt/base projection for a tombstone."""

        setting_type = metadata.get("setting_type")
        if setting_type not in {"prompt", "base"}:
            return
        logical_path = str(metadata.get("logical_path") or "")
        if not logical_path:
            missing.append({"setting_type": setting_type, "error": "删除版本缺少 logical_path"})
            return
        target = (self.root / logical_path).resolve()
        if not self._inside(target, self.root):
            missing.append({"logical_path": logical_path, "error": "删除路径超出设置目录"})
            return
        try:
            if target.is_symlink():
                missing.append({"logical_path": logical_path, "error": "设置路径是符号链接"})
                return
            if target.is_file():
                target.unlink()
                parent = target.parent
                while parent != self.root and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
        except OSError as exc:
            missing.append({"logical_path": logical_path, "error": str(exc)})

    def _remove_series_entities(self, series_ids: Iterable[str], missing: List[Any]) -> None:
        """Remove only tombstoned IDs from the aggregate local series file."""

        path = self.root / "series.json"
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("series.json must contain a list")
            remove = {str(value) for value in series_ids}
            filtered = [item for item in raw
                        if not (isinstance(item, dict) and str(item.get("id")) in remove)]
            if filtered != raw:
                self._write_json(path, filtered)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            missing.append({"logical_path": "series.json", "error": str(exc)})

    # ------------------------------------------------------------------
    # Marker/state and serialization helpers
    # ------------------------------------------------------------------
    def _markers(self) -> Dict[str, Any]:
        state = getattr(self.runtime, "state", None)
        if not isinstance(state, dict):
            raise ValueError("runtime state is unavailable")
        markers = state.setdefault("settings_versions", {})
        if not isinstance(markers, dict):
            raise ValueError("runtime settings_versions is malformed")
        return markers

    @staticmethod
    def _marker_for(markers: Mapping[str, Any], entity_id: str) -> Dict[str, Any]:
        value = markers.get(entity_id, {})
        if isinstance(value, str):
            return {"revision_id": value}
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _new_marker(revision_id: str, fingerprint: str, entity: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "revision_id": revision_id,
            "fingerprint": fingerprint,
            "setting_type": entity.get("metadata", {}).get("setting_type"),
            "logical_path": entity.get("logical_path") or entity.get("metadata", {}).get("logical_path"),
        }

    def _merge_used_reference_state(self, used_hashes: Iterable[str]) -> None:
        state = self.runtime.state
        known = state.setdefault("settings_used_references", {})
        if not isinstance(known, dict):
            known = {}
            state["settings_used_references"] = known
        for digest in used_hashes:
            known[digest] = True

    def _known_used_hashes(self) -> set:
        known = self.runtime.state.get("settings_used_references", {})
        return set(known) if isinstance(known, dict) else set()

    def _save_state(self) -> None:
        save = getattr(self.runtime, "save", None)
        if callable(save):
            save()

    def _require_account(self) -> None:
        if not self.account_id:
            raise ValueError("请先绑定平台账号")

    @staticmethod
    def _entity_id(setting_type: str, key: str) -> str:
        digest = hashlib.sha256(f"{setting_type}\0{key}".encode("utf-8")).hexdigest()[:32]
        return f"settings-{digest}"

    @staticmethod
    def _token(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _fingerprint(metadata: Mapping[str, Any], files: Mapping[str, Any]) -> str:
        data = json.dumps([metadata, files], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    def _put_bytes(self, data: bytes, suffix: str) -> Dict[str, Any]:
        fd, name = tempfile.mkstemp(prefix=".settings-source-", suffix=suffix, dir=str(self.root.parent))
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            return self.library.put_file(path)
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        if yaml is None:
            raise RuntimeError("PyYAML 未安装")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("prefs.yaml must contain an object")
        return data

    @staticmethod
    def _sanitize_prefs(data: Mapping[str, Any]) -> Dict[str, Any]:
        result = {key: copy.deepcopy(data[key]) for key in PREF_KEYS if key in data}
        # Device-specific browser mode never enters a shared account setting.
        if result.get("reference_lib_path"):
            result["reference_lib_path"] = "reference_library"
        return result

    @staticmethod
    def _dump_yaml(data: Mapping[str, Any]) -> bytes:
        if yaml is None:
            raise RuntimeError("PyYAML 未安装")
        return yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False).encode("utf-8")

    @staticmethod
    def _apply_prefs_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(dict(payload))
        if result.get("reference_lib_path"):
            # The caller writes this relative path as an absolute path below.
            result["reference_lib_path"] = "reference_library"
        result.pop("browser_headless", None)
        return result

    def _write_yaml(self, path: Path, payload: Mapping[str, Any]) -> None:
        data = self._dump_yaml(payload)
        self._atomic_write(path, data)

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write(path, self._json_bytes(payload))

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise LibraryValidationError(f"setting path is a symlink: {path}")
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_file(source: Path, destination: Path) -> None:
        if source.is_symlink() or not source.is_file():
            raise LibraryValidationError(f"setting source is not a regular file: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise LibraryValidationError(f"setting destination is a symlink: {destination}")
        if destination.exists():
            return
        SharedSettings._atomic_write(destination, source.read_bytes())

    def _copy_tree_if_missing(self, source: Path, destination: Path) -> Tuple[int, int]:
        seeded = 0
        skipped = 0
        for path in self._iter_files(source):
            relative = path.relative_to(source)
            target = destination / relative
            if target.exists():
                skipped += 1
            else:
                self._copy_file(path, target)
                seeded += 1
        return seeded, skipped

    def _iter_files(self, root: Path) -> List[Path]:
        if not root.is_dir() or root.is_symlink():
            return []
        files: List[Path] = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file() or self._is_private(path):
                continue
            files.append(path)
        return files

    @staticmethod
    def _is_private(path: Path) -> bool:
        names = {part.casefold() for part in path.parts}
        return bool(names & {name.casefold() for name in PRIVATE_NAMES}) or any(
            ".sync-conflict-" in name or name.startswith(("~syncthing~", ".syncthing."))
            for name in names
        )

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _hash_path(path: Path) -> Tuple[str, int]:
        # Use the shared stat-keyed integrity cache so repeated status/capture
        # calls do not rehash unchanged custom assets.
        from .resources import hash_file

        try:
            return hash_file(path)
        except ValueError as exc:
            raise OSError(str(exc)) from exc
