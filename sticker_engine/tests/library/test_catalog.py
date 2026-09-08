import json
from pathlib import Path

import pytest

from sticker_engine.library.catalog import (
    LibraryIntegrityError,
    LibraryStateError,
    LibraryValidationError,
    ResourceLibrary,
)


def _raw(tmp_path: Path, name: str = "raw.bin", data: bytes = b"raw") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_round_trip_materializes_a_complete_work_and_keeps_accounts_separate(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    raw = _raw(tmp_path, data=b"image")

    resource = library.put_file(raw)
    revision = library.write_revision(
        "account-a",
        "work-a",
        {"title": "hello"},
        {"nested/raw.png": resource},
    )

    work = library.read_work("account-a", "work-a")
    assert work["state"] == "available"
    assert work["revision"]["revision_id"] == revision["revision_id"]
    assert work["heads"] == [revision]
    assert library.read_work("account-b", "work-a")["state"] == "placeholder"
    assert [item["work_id"] for item in library.list_works("account-a")] == ["work-a"]
    assert library.list_works("account-b") == []

    target = tmp_path / "materialized"
    result = library.materialize("account-a", "work-a", target)
    assert result == target
    assert (target / "nested/raw.png").read_bytes() == b"image"


def test_empty_episode_revision_is_a_placeholder_even_without_flag(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)

    revision = library.write_revision(
        "account",
        "work",
        {"kind": "episode", "resource_placeholder": False},
        {},
    )

    work = library.read_work("account", "work")
    assert work["state"] == "placeholder"
    assert work["revision"]["revision_id"] == revision["revision_id"]


@pytest.mark.parametrize(
    "field_value",
    [
        "/old-machine/banner.png",
        r"C:\\old-machine\\banner.png",
        r"C:/old-machine/banner.png",
        "../outside/banner.png",
        "nested/../../outside/banner.png",
        r"\\\\server\\share\\banner.png",
    ],
)
def test_episode_custom_metadata_paths_must_be_portable_relative_paths(
    tmp_path, field_value
):
    library = ResourceLibrary(tmp_path / "library", create=True)

    with pytest.raises(LibraryValidationError):
        library.write_revision(
            "account",
            "work",
            {"kind": "episode", "banner_custom": field_value},
            {},
        )


def test_episode_custom_metadata_accepts_portable_relative_path(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)

    revision = library.write_revision(
        "account",
        "work",
        {"kind": "episode", "banner_custom": "_external/banner.png"},
        {},
    )

    assert revision["metadata"]["banner_custom"] == "_external/banner.png"


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "kind": "settings",
            "setting_type": "series",
            "logical_path": "../series.json",
            "payload": {"role_asset_map": {"hero": {"banner": "_assets/../../secret.png"}}},
        },
        {
            "kind": "settings",
            "setting_type": "prefs",
            "logical_path": "prefs.yaml",
            "payload": {"reference_lib_path": "/Users/me/reference_library"},
        },
        {
            "kind": "settings",
            "setting_type": "series",
            "logical_path": "series.json",
            "payload": {"role_asset_map": {"hero": {"banner": r"C:\\old\\banner.png"}}},
        },
    ],
)
def test_settings_metadata_paths_must_be_portable_before_apply(tmp_path, metadata):
    library = ResourceLibrary(tmp_path / "library", create=True)

    with pytest.raises(LibraryValidationError):
        library.write_revision("account", "settings-1", metadata, {})


def test_settings_metadata_accepts_catalog_relative_paths(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    revision = library.write_revision(
        "account",
        "settings-1",
        {
            "kind": "settings",
            "setting_type": "series",
            "logical_path": "series/entity-series-a.json",
            "payload": {
                "role_asset_map": {"hero": {"banner": "_assets/banner.png"}}
            },
        },
        {},
    )

    assert revision["metadata"]["logical_path"] == "series/entity-series-a.json"


def test_manifest_first_arrival_stays_pending_until_objects_arrive(tmp_path):
    source = ResourceLibrary(tmp_path / "source", create=True)
    raw = _raw(tmp_path, data=b"image")
    revision = source.write_revision(
        "account",
        "work",
        {},
        {"raw.png": source.put_file(raw)},
    )

    destination = ResourceLibrary(tmp_path / "destination", create=True)
    manifest = destination.root / "accounts/account/works/work/revisions"
    manifest.mkdir(parents=True)
    (manifest / f"{revision['revision_id']}.json").write_text(
        json.dumps(revision), encoding="utf-8"
    )

    pending = destination.read_work("account", "work")
    assert pending["state"] == "pending"
    assert revision["files"]["raw.png"]["sha256"] in pending["missing"]
    with pytest.raises(LibraryStateError):
        destination.materialize("account", "work", tmp_path / "out")

    destination.merge_from(source)
    assert destination.read_work("account", "work")["state"] == "available"


def test_missing_parent_is_pending_and_does_not_activate_a_revision(tmp_path):
    source = ResourceLibrary(tmp_path / "source", create=True)
    raw = _raw(tmp_path, data=b"image")
    parent = source.write_revision("account", "work", {}, {"raw.png": source.put_file(raw)})
    child = source.write_revision(
        "account",
        "work",
        {"title": "child"},
        {"raw.png": source.put_file(raw)},
        parents=[parent["revision_id"]],
    )

    destination = ResourceLibrary(tmp_path / "destination", create=True)
    manifest = destination.root / "accounts/account/works/work/revisions"
    manifest.mkdir(parents=True)
    (manifest / f"{child['revision_id']}.json").write_text(
        json.dumps(child), encoding="utf-8"
    )
    destination.merge_from(source)
    # The object is present after the merge, but the referenced parent is not
    # copied by this isolated manifest setup and therefore remains pending.
    parent_path = (
        destination.root
        / "accounts/account/works/work/revisions"
        / f"{parent['revision_id']}.json"
    )
    parent_path.unlink()
    assert destination.read_work("account", "work")["state"] == "pending"
    assert parent["revision_id"] in destination.read_work("account", "work")["missing"]


def test_hash_corruption_fails_closed(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    raw = _raw(tmp_path, data=b"image")
    resource = library.put_file(raw)
    library.write_revision("account", "work", {}, {"raw.png": resource})
    object_path = library.root / "objects" / resource["sha256"][:2] / resource["sha256"]
    object_path.write_bytes(b"tampered")

    with pytest.raises(LibraryIntegrityError):
        library.read_work("account", "work")
    with pytest.raises(LibraryIntegrityError):
        library.materialize("account", "work", tmp_path / "out")


def test_divergent_edits_are_retained_and_resolve_creates_a_merge_revision(tmp_path):
    left = ResourceLibrary(tmp_path / "left", create=True)
    raw_a = _raw(tmp_path, "a.bin", b"a")
    raw_b = _raw(tmp_path, "b.bin", b"b")
    base = left.write_revision("account", "work", {}, {"raw.png": left.put_file(raw_a)})

    right = ResourceLibrary(tmp_path / "right", create=True)
    right.merge_from(left)
    left.write_revision(
        "account",
        "work",
        {"branch": "left"},
        {"raw.png": left.put_file(raw_a)},
        parents=[base["revision_id"]],
    )
    right.write_revision(
        "account",
        "work",
        {"branch": "right"},
        {"raw.png": right.put_file(raw_b)},
        parents=[base["revision_id"]],
    )

    left.merge_from(right)
    conflicted = left.read_work("account", "work")
    assert conflicted["state"] == "conflict"
    assert len(conflicted["heads"]) == 2

    chosen = conflicted["heads"][0]["revision_id"]
    merged = left.resolve("account", "work", chosen)
    assert set(merged["parents"]) == {head["revision_id"] for head in conflicted["heads"]}
    assert left.read_work("account", "work")["state"] == "available"


def test_delete_and_edit_branches_conflict_and_can_be_resolved(tmp_path):
    left = ResourceLibrary(tmp_path / "left", create=True)
    raw = _raw(tmp_path, data=b"image")
    base = left.write_revision("account", "work", {}, {"raw.png": left.put_file(raw)})
    right = ResourceLibrary(tmp_path / "right", create=True)
    right.merge_from(left)

    left.write_revision(
        "account",
        "work",
        {},
        {"raw.png": left.put_file(raw)},
        parents=[base["revision_id"]],
        deleted=True,
    )
    right.write_revision(
        "account",
        "work",
        {"edited": True},
        {"raw.png": right.put_file(raw)},
        parents=[base["revision_id"]],
    )
    left.merge_from(right)

    work = left.read_work("account", "work")
    assert work["state"] == "conflict"
    edited = next(head for head in work["heads"] if not head["deleted"])
    merged = left.resolve("account", "work", edited["revision_id"])
    assert merged["deleted"] is False
    assert left.read_work("account", "work")["state"] == "available"


def test_repeated_import_is_idempotent_and_preserves_target_identity(tmp_path):
    source = ResourceLibrary(tmp_path / "source", create=True)
    raw = _raw(tmp_path, data=b"image")
    source.write_revision("account", "work", {}, {"raw.png": source.put_file(raw)})
    destination = ResourceLibrary(tmp_path / "destination", create=True)
    original_id = destination.library_id

    first = destination.merge_from(source)
    second = destination.merge_from(source)
    assert first["revisions"] == 1
    assert second["revisions"] == 0
    assert destination.library_id == original_id
    assert destination.read_work("account", "work")["state"] == "available"


@pytest.mark.parametrize("logical_path", [
    "/absolute.png",
    "../escape.png",
    "folder/../../escape.png",
    r"C:\\absolute.png",
    "CON.txt",
    "folder/con.txt",
])
def test_unsafe_logical_paths_are_rejected(tmp_path, logical_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    raw = _raw(tmp_path, data=b"image")
    with pytest.raises(LibraryValidationError):
        library.write_revision(
            "account",
            "work",
            {},
            {logical_path: library.put_file(raw)},
        )


def test_case_colliding_paths_and_nonempty_materialize_target_fail_closed(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    raw = _raw(tmp_path, data=b"image")
    resource = library.put_file(raw)
    with pytest.raises(LibraryValidationError):
        library.write_revision(
            "account",
            "work",
            {},
            {"A.png": resource, "a.png": resource},
        )
    library.write_revision("account", "work", {}, {"raw.png": resource})
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(LibraryValidationError):
        library.materialize("account", "work", target)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_sync_conflict_files_are_reported_without_being_ingested(tmp_path):
    library = ResourceLibrary(tmp_path / "library", create=True)
    revisions = library.root / "accounts/account/works/work/revisions"
    revisions.mkdir(parents=True)
    (revisions / "revision.sync-conflict-20260908.json").write_text("{}", encoding="utf-8")
    work = library.read_work("account", "work")
    assert work["state"] == "placeholder"
    assert work["sync_conflicts"]
