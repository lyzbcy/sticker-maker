from pathlib import Path

import pytest

from sticker_engine.library.transfer import TransferManager


def test_preview_persists_a_checksummed_plan(tmp_path: Path) -> None:
    source = tmp_path / "episode"
    source.mkdir()
    payload = source / "final.png"
    payload.write_bytes(b"episode")
    state = tmp_path / "state"
    target = tmp_path / "backup"

    manager = TransferManager(state)
    plan = manager.preview(
        [
            {
                "path": source,
                "account_id": "account-1",
                "work_id": "work-1",
                "metadata": {"album_name": "test"},
            }
        ],
        target,
    )

    assert plan["plan_id"]
    assert plan["mode"] == "backup"
    assert plan["target"] == str(target.resolve())
    assert plan["bytes"] == len(b"episode")
    assert plan["missing"] == []
    assert plan["entries"]
    assert plan["entries"][0]["sha256"]
    assert list((state / "plans").glob("*.json"))


def _library(root: Path):
    from sticker_engine.library.catalog import ResourceLibrary

    return ResourceLibrary(root)


def _source(tmp_path: Path, name: str = "episode", *, account: str = "account-1", work: str = "work-1"):
    root = tmp_path / name
    (root / "原图").mkdir(parents=True)
    (root / "原图" / "raw.png").write_bytes(b"raw")
    (root / "最终版").mkdir()
    (root / "最终版" / "final.png").write_bytes(b"final")
    return root, {
        "path": root,
        "account_id": account,
        "work_id": work,
        "metadata": {"album_name": name},
    }


def test_backup_copies_a_complete_work_without_activation(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    target = tmp_path / "backup"
    called = []

    plan = TransferManager(tmp_path / "state").preview([spec], target)
    result = TransferManager(tmp_path / "state").execute(
        plan["plan_id"], activate=lambda _: called.append(True)
    )

    assert result["state"] == "completed"
    assert result["target"] == str(target.resolve())
    assert result["missing"] == []
    assert result["errors"] == []
    assert result["copied"]
    assert called == []
    assert source.exists()
    assert _library(target).read_work("account-1", "work-1")["state"] == "available"


def test_import_without_parent_proof_preserves_a_version_conflict_and_is_idempotent(
    tmp_path: Path,
) -> None:
    from sticker_engine.library.catalog import ResourceLibrary

    target = tmp_path / "target"
    target_library = ResourceLibrary(target, create=True)
    old = tmp_path / "old.png"
    old.write_bytes(b"old")
    base = target_library.write_revision(
        "account-1",
        "work-1",
        {"kind": "episode", "album_name": "old"},
        {"raw.png": target_library.put_file(old)},
    )

    source, spec = _source(tmp_path, account="account-1", work="work-1")
    (source / "原图" / "raw.png").write_bytes(b"new")
    spec["metadata"] = {"kind": "episode", "album_name": "new"}

    state = tmp_path / "state"
    manager = TransferManager(state)
    plan = manager.preview([spec], target)
    first = manager.execute(plan["plan_id"])

    work = _library(target).read_work("account-1", "work-1")
    assert first["state"] == "completed"
    assert work["state"] == "conflict"
    assert len(work["heads"]) == 2
    assert {head["metadata"]["album_name"] for head in work["heads"]} == {"old", "new"}

    repeat_plan = manager.preview([spec], target)
    second = manager.execute(repeat_plan["plan_id"])
    work_after_repeat = _library(target).read_work("account-1", "work-1")
    assert second["created_revision_ids"] == []
    assert len(work_after_repeat["heads"]) == 2
    assert {head["metadata"]["album_name"] for head in work_after_repeat["heads"]} == {
        "old",
        "new",
    }


def test_empty_legacy_work_is_not_reported_as_an_available_resource(tmp_path: Path) -> None:
    source = tmp_path / "episode-empty"
    source.mkdir()
    target = tmp_path / "target"
    spec = {
        "path": source,
        "account_id": "account-1",
        "work_id": "work-1",
        "metadata": {"kind": "episode", "album_name": "empty"},
    }

    state = tmp_path / "state"
    manager = TransferManager(state)
    plan = manager.preview([spec], target)
    result = manager.execute(plan["plan_id"])

    assert result["state"] == "completed"
    assert _library(target).read_work("account-1", "work-1")["state"] == "placeholder"


def test_migration_activation_failure_preserves_source_and_skips_cleanup(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)

    def fail_activation(_target):
        raise RuntimeError("config switch failed")

    result = TransferManager(state).execute(plan["plan_id"], activate=fail_activation)

    assert result["state"] in {"activation_failed", "failed"}
    assert any("config switch failed" in str(error) for error in result["errors"])
    assert source.exists()
    assert (source / "原图" / "raw.png").exists()
    assert (source / "最终版" / "final.png").exists()


def test_migration_cleanup_is_opt_in_and_preserves_external_extra(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    external = tmp_path / "shared-reference.png"
    external.write_bytes(b"external")
    spec["extra_files"] = {"参考图/shared.png": external}
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)

    result = TransferManager(state).execute(plan["plan_id"], activate=lambda _: None)

    assert result["state"] == "completed"
    assert not (source / "原图" / "raw.png").exists()
    assert not (source / "最终版" / "final.png").exists()
    assert source.exists()
    assert external.exists()
    assert (target / "objects").exists()


def test_cancelled_execution_resumes_from_persisted_plan(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    (source / "extra.bin").write_bytes(b"extra")
    state = tmp_path / "state"
    target = tmp_path / "backup"
    manager = TransferManager(state)
    plan = manager.preview([spec], target)
    calls = {"count": 0}

    def stop_after_first():
        calls["count"] += 1
        return calls["count"] > 1

    first = manager.execute(plan["plan_id"], should_stop=stop_after_first)
    assert first["state"] == "cancelled"
    assert first["copied"]

    resumed = TransferManager(state).execute(plan["plan_id"])
    assert resumed["state"] == "completed"
    assert _library(target).read_work("account-1", "work-1")["state"] == "available"


def test_changed_source_refuses_cleanup_and_reports_change(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)
    (source / "最终版" / "final.png").write_bytes(b"changed")

    result = TransferManager(state).execute(plan["plan_id"], activate=lambda _: None)

    assert result["state"] in {"source_changed", "failed", "incomplete"}
    assert result["cleaned"] == []
    assert any("changed" in str(error).lower() for error in result["errors"])
    assert (source / "最终版" / "final.png").read_bytes() == b"changed"


def test_missing_external_dependency_is_reported_and_blocks_activation(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    missing = tmp_path / "not-yet-present.png"
    spec["extra_files"] = {"参考图/missing.png": missing}
    state = tmp_path / "state"
    target = tmp_path / "migrated"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)

    assert plan["missing"]
    result = TransferManager(state).execute(plan["plan_id"], activate=lambda _: None)

    assert result["missing"]
    assert result["cleaned"] == []
    assert result["state"] in {"incomplete", "missing", "failed"}
    assert (source / "原图" / "raw.png").exists()


def test_restored_external_dependency_can_resume_the_same_plan(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    dependency = tmp_path / "later.png"
    spec["extra_files"] = {"参考图/later.png": dependency}
    state = tmp_path / "state"
    target = tmp_path / "backup"
    manager = TransferManager(state)
    plan = manager.preview([spec], target)
    dependency.write_bytes(b"later")

    result = TransferManager(state).execute(plan["plan_id"])

    assert result["state"] == "completed"
    assert result["missing"] == []
    assert _library(target).read_work("account-1", "work-1")["state"] == "available"


def test_source_and_target_must_not_be_equal_or_nested(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    manager = TransferManager(tmp_path / "state")

    with pytest.raises(ValueError):
        manager.preview([spec], source)
    with pytest.raises(ValueError):
        manager.preview([spec], source / "nested")
    with pytest.raises(ValueError):
        manager.preview([dict(spec, path=source / "nested")], source)


def test_credentials_browser_and_syncthing_files_are_not_captured(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    (source / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (source / "auth.json").write_text("{}", encoding="utf-8")
    (source / "Cookies").write_bytes(b"cookie")
    (source / "browser-state").mkdir()
    (source / "browser-state" / "History").write_bytes(b"history")
    (source / ".stfolder").write_text("syncthing", encoding="utf-8")
    (source / ".stversions").mkdir()
    (source / ".stversions" / "old.png").write_bytes(b"old")
    (source / "safe.txt").write_text("safe", encoding="utf-8")

    plan = TransferManager(tmp_path / "state").preview([spec], tmp_path / "backup")
    logical = {entry["logical_path"] for entry in plan["entries"]}

    assert "safe.txt" in logical
    assert all(
        not any(token in path.lower() for token in (".env", "auth", "cookie", "browser", ".st"))
        for path in logical
    )


def test_repeated_execution_does_not_create_duplicate_revision(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    target = tmp_path / "backup"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target)

    first = TransferManager(state).execute(plan["plan_id"])
    second = TransferManager(state).execute(plan["plan_id"])
    work = _library(target).read_work("account-1", "work-1")

    assert first["state"] == second["state"] == "completed"
    assert first["created_revision_ids"] == second["created_revision_ids"]
    assert len(work["heads"]) == 1


def test_nested_files_are_portable_and_symlink_is_not_followed(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    nested = source / "处理结果" / "nested"
    nested.mkdir(parents=True)
    (nested / "sticker.png").write_bytes(b"sticker")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (source / "escape.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    plan = TransferManager(tmp_path / "state").preview([spec], tmp_path / "backup")
    assert "处理结果/nested/sticker.png" in {e["logical_path"] for e in plan["entries"]}
    assert any(item["logical_path"] == "escape.txt" for item in plan["missing"])


def test_existing_library_revision_is_merged_without_creating_a_new_revision(tmp_path: Path) -> None:
    from sticker_engine.library.catalog import ResourceLibrary

    source_library = ResourceLibrary(tmp_path / "source-library", create=True)
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"raw")
    metadata = {"kind": "episode", "album_name": "already captured"}
    resource = source_library.put_file(raw)
    revision = source_library.write_revision(
        "account-1", "work-1", metadata, {"原图/raw.png": resource}
    )
    source = tmp_path / "episode"
    (source / "原图").mkdir(parents=True)
    (source / "原图" / "raw.png").write_bytes(b"raw")
    spec = {
        "path": source,
        "account_id": "account-1",
        "work_id": "work-1",
        "metadata": metadata,
        "library_root": source_library.root,
        "revision_id": revision["revision_id"],
    }

    plan = TransferManager(tmp_path / "state").preview([spec], tmp_path / "backup")
    result = TransferManager(tmp_path / "state").execute(plan["plan_id"])
    work = _library(tmp_path / "backup").read_work("account-1", "work-1")

    assert result["state"] == "completed"
    assert work["revision"]["revision_id"] == revision["revision_id"]
    assert result["created_revision_ids"] == []


def test_root_meta_json_is_verified_for_cleanup_but_not_stored_as_an_object(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    meta = source / "meta.json"
    meta.write_text('{"absolute": "/old-machine"}', encoding="utf-8")
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)

    meta_entries = [entry for entry in plan["entries"] if entry["logical_path"] == "meta.json"]
    assert len(meta_entries) == 1
    assert meta_entries[0]["capture"] is False

    result = TransferManager(state).execute(plan["plan_id"], activate=lambda _: None)
    assert result["state"] == "completed"
    work = _library(target).read_work("account-1", "work-1")
    assert "meta.json" not in work["revision"]["files"]
    assert not meta.exists()


def test_partial_cleanup_is_resumable_after_a_progress_failure(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    (source / "a.bin").write_bytes(b"a")
    (source / "b.bin").write_bytes(b"b")
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)
    raised = {"value": False}

    def fail_once(event):
        if event.get("phase") == "cleanup" and not raised["value"]:
            raised["value"] = True
            raise RuntimeError("progress channel closed")

    first = TransferManager(state).execute(
        plan["plan_id"], activate=lambda _: None, progress=fail_once
    )
    assert first["state"] == "cleanup_partial"
    assert first["cleanup_errors"]
    assert (source / "b.bin").exists() or (source / "a.bin").exists()

    resumed = TransferManager(state).execute(plan["plan_id"])
    assert resumed["state"] == "completed"
    assert not (source / "a.bin").exists()
    assert not (source / "b.bin").exists()


def test_new_source_file_appearing_during_cleanup_is_preserved(tmp_path: Path) -> None:
    source, spec = _source(tmp_path)
    (source / "a.bin").write_bytes(b"a")
    (source / "b.bin").write_bytes(b"b")
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview([spec], target, mode="migration", cleanup=True)
    created = {"value": False}

    def add_file_after_first_cleanup(event):
        if event.get("phase") == "cleanup" and not created["value"]:
            created["value"] = True
            (source / "new.bin").write_bytes(b"new")

    result = TransferManager(state).execute(
        plan["plan_id"], activate=lambda _: None, progress=add_file_after_first_cleanup
    )

    assert result["state"] == "cleanup_partial"
    assert (source / "new.bin").exists()
    assert result["cleanup_errors"]


def test_full_library_preview_and_copy_preserves_history_without_episode_sources(tmp_path: Path) -> None:
    from sticker_engine.library.catalog import ResourceLibrary

    source_root = tmp_path / "source-library"
    source = ResourceLibrary(source_root, create=True)
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"raw")
    resource = source.put_file(raw)
    first = source.write_revision(
        "account-1",
        "work-1",
        {"kind": "episode", "album_name": "history"},
        {"原图/raw.png": resource},
    )
    source.write_revision(
        "account-1",
        "work-1",
        {"kind": "episode", "album_name": "deleted"},
        {},
        parents=[first["revision_id"]],
        deleted=True,
    )
    source.write_revision(
        "account-1",
        "settings-prefs",
        {"kind": "settings", "setting_type": "prefs"},
        {},
        parents=[],
    )
    source.write_revision(
        "account-1",
        "operation-1",
        {"kind": "operation", "target_work": "work-1", "phase": "unknown"},
        {},
        parents=[],
    )

    state = tmp_path / "state"
    target = tmp_path / "backup"
    manager = TransferManager(state)
    plan = manager.preview([], target, library_roots=[source_root])

    assert plan["sources"] == []
    assert plan["library_roots"] == [str(source_root.resolve())]
    assert plan["object_count"] == 1
    assert plan["manifest_count"] >= 4
    assert plan["bytes"] == sum(int(entry["size"]) for entry in plan["entries"])
    assert any(entry["logical_path"].startswith("objects/") for entry in plan["entries"])
    assert any(entry["logical_path"].endswith(".json") for entry in plan["entries"])
    assert plan["missing"] == []

    result = manager.execute(plan["plan_id"])

    assert result["state"] == "completed"
    assert result["errors"] == []
    copied = ResourceLibrary(target, create=False)
    copied_work = copied.read_work("account-1", "work-1")
    assert copied_work["state"] == "deleted"
    assert {head["metadata"]["album_name"] for head in copied_work["heads"]} == {"deleted"}
    assert copied.read_work("account-1", "settings-prefs")["revision"] is not None
    assert copied.read_work("account-1", "operation-1")["revision"] is not None
    assert copied.library_id == source.library_id


def test_full_library_missing_object_blocks_migration_activation_and_cleanup(tmp_path: Path) -> None:
    from sticker_engine.library.catalog import ResourceLibrary

    source_root = tmp_path / "source-library"
    source = ResourceLibrary(source_root, create=True)
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"raw")
    resource = source.put_file(raw)
    source.write_revision(
        "account-1",
        "work-1",
        {"kind": "episode", "album_name": "broken"},
        {"原图/raw.png": resource},
    )
    object_path = source_root / "objects" / resource["sha256"][:2] / resource["sha256"]
    object_path.unlink()

    state = tmp_path / "state"
    target = tmp_path / "migrated"
    manager = TransferManager(state)
    plan = manager.preview_library([source_root], target, mode="migration", cleanup=True)

    assert plan["missing"]
    assert any(item["reason"] == "referenced_object_missing" for item in plan["missing"])
    called = []
    result = manager.execute(plan["plan_id"], activate=lambda _: called.append(True))

    assert result["state"] in {"incomplete", "failed"}
    assert called == []
    assert object_path.parent.exists()
    assert (source_root / "library.json").exists()
    assert not result["activated"]


def test_full_library_migration_activates_then_cleans_the_verified_source(tmp_path: Path) -> None:
    from sticker_engine.library.catalog import ResourceLibrary

    source_root = tmp_path / "source-library"
    source = ResourceLibrary(source_root, create=True)
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"raw")
    source.write_revision(
        "account-1",
        "settings-only",
        {"kind": "settings", "setting_type": "prefs"},
        {"raw.png": source.put_file(raw)},
        parents=[],
    )
    target = tmp_path / "migrated"
    state = tmp_path / "state"
    plan = TransferManager(state).preview_library(
        [source_root], target, mode="migration", cleanup=True
    )
    activated = []

    result = TransferManager(state).execute(
        plan["plan_id"], activate=lambda path: activated.append(path)
    )

    assert result["state"] == "completed"
    assert activated == [target.resolve()]
    assert result["cleaned"]
    assert not (source_root / "library.json").exists()
    assert not any(source_root.rglob("*.json"))
    assert ResourceLibrary(target, create=False).read_work("account-1", "settings-only")["state"] == "available"


def test_full_library_migration_preserves_unknown_files(tmp_path):
    from sticker_engine.library.catalog import ResourceLibrary
    library = ResourceLibrary(tmp_path / 'source', create=True)
    for name in ('notes.bin', 'notes.json'):
        (library.root / name).write_bytes(b'unregistered user file')
    manager = TransferManager(tmp_path / 'state')
    plan = manager.preview_library([library.root], tmp_path / 'target', mode='migration', cleanup=True)
    unknown = [entry for entry in plan['entries'] if entry['logical_path'].startswith('notes.')]
    assert len(unknown) == 2 and all(not entry['managed'] for entry in unknown)
    result = manager.execute(plan['plan_id'], activate=lambda target: None)
    assert result['state'] == 'completed', result
    for name in ('notes.bin', 'notes.json'):
        assert (library.root / name).read_bytes() == b'unregistered user file'
