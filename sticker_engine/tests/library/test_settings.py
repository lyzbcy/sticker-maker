import json
import shutil
from pathlib import Path

import pytest

from sticker_engine.library.catalog import ResourceLibrary
from sticker_engine.library.settings import SharedSettings, settings_dir


class FakeRuntime:
    def __init__(self, user_data: Path, library: ResourceLibrary, account_id: str = "account"):
        self.user_data = Path(user_data)
        self.local = self.user_data / "resource_library"
        self.library = library
        self.account_id = account_id
        self.account_label = "测试账号"
        self.state = {
            "library_id": library.library_id,
            "account_id": account_id,
            "account_label": self.account_label,
            "settings_versions": {},
        }

    def save(self):
        self.local.mkdir(parents=True, exist_ok=True)
        (self.local / "device.json").write_text(
            json.dumps(self.state, ensure_ascii=False), encoding="utf-8"
        )


def _runtime(tmp_path: Path, library: ResourceLibrary, name: str = "computer") -> FakeRuntime:
    return FakeRuntime(tmp_path / name, library)


def test_seed_capture_apply_round_trip_excludes_device_and_secret_prefs(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    source = _runtime(tmp_path, library, "source")
    external = tmp_path / "external"
    external.mkdir()
    (external / "ref.png").write_bytes(b"reference")
    asset = tmp_path / "old-computer-banner.png"
    asset.write_bytes(b"banner")
    source.user_data.mkdir(parents=True)
    (source.user_data / "prefs.yaml").write_text(
        "grid_size: 3\n"
        "browser_headless: true\n"
        "api_token: should-not-share\n"
        f"reference_lib_path: {external}\n",
        encoding="utf-8",
    )
    (source.user_data / "series.json").write_text(
        json.dumps(
            [{"id": "series-a", "name": "系列", "role_asset_map": {"hero": str(asset)}}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source.user_data / "reference_library").mkdir()
    (source.user_data / "reference_library" / "local.png").write_bytes(b"local")
    (source.user_data / "custom_bases").mkdir()
    (source.user_data / "custom_bases" / "base.png").write_bytes(b"base")
    (source.user_data / "prompts").mkdir()
    (source.user_data / "prompts" / "prompt-a.json").write_text(
        json.dumps({"id": "prompt-a", "name": "Prompt"}), encoding="utf-8"
    )

    adapter = SharedSettings(source)
    seeded = adapter.seed_legacy()
    captured = adapter.capture()
    assert seeded["seeded"] >= 1
    assert captured["captured"] >= 5

    settings_work = source.library.list_works(source.account_id)
    assert settings_work
    serialized = json.dumps(settings_work, ensure_ascii=False)
    assert "should-not-share" not in serialized
    assert "browser_headless" not in serialized

    destination = _runtime(tmp_path, library, "destination")
    applied = SharedSettings(destination).apply()
    assert not applied["conflicts"]
    assert not applied["missing"]
    prefs = (settings_dir(destination) / "prefs.yaml").read_text(encoding="utf-8")
    assert "browser_headless" not in prefs
    assert "should-not-share" not in prefs
    assert str(settings_dir(destination) / "reference_library") in prefs
    assert json.loads((settings_dir(destination) / "series.json").read_text(encoding="utf-8"))[0]["name"] == "系列"
    role_asset = json.loads((settings_dir(destination) / "series.json").read_text(encoding="utf-8"))[0]["role_asset_map"]["hero"]
    assert Path(role_asset).is_absolute()
    assert Path(role_asset).is_file()
    assert (settings_dir(destination) / "reference_library" / "ref.png").read_bytes() == b"reference"

    # Seeding never consumes or moves the legacy source.
    assert (source.user_data / "reference_library" / "local.png").exists()
    assert asset.exists()


def test_repeat_capture_does_not_create_new_setting_revisions(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    runtime = _runtime(tmp_path, library)
    (runtime.user_data / "prefs.yaml").parent.mkdir(parents=True)
    (runtime.user_data / "prefs.yaml").write_text("grid_size: 4\n", encoding="utf-8")
    SharedSettings(runtime).seed_legacy()
    first = SharedSettings(runtime).capture()
    second = SharedSettings(runtime).capture()
    assert first["captured"] == 1
    assert second["captured"] == 0
    assert second["unchanged"] >= 1


def test_concurrent_same_series_edit_is_reported_without_overwriting_local_file(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    first = _runtime(tmp_path, library, "first")
    second = _runtime(tmp_path, library, "second")
    for runtime in (first, second):
        runtime.user_data.mkdir(parents=True)
        (runtime.user_data / "series.json").write_text(
            json.dumps([{"id": "series-a", "name": "原始"}], ensure_ascii=False),
            encoding="utf-8",
        )
        SharedSettings(runtime).seed_legacy()
        SharedSettings(runtime).capture()
    SharedSettings(second).apply()

    (settings_dir(first) / "series.json").write_text(
        json.dumps([{"id": "series-a", "name": "电脑一"}], ensure_ascii=False),
        encoding="utf-8",
    )
    SharedSettings(first).capture()
    (settings_dir(second) / "series.json").write_text(
        json.dumps([{"id": "series-a", "name": "电脑二"}], ensure_ascii=False),
        encoding="utf-8",
    )
    result = SharedSettings(second).capture()
    assert result["conflicts"]
    assert json.loads(
        (settings_dir(second) / "series.json").read_text(encoding="utf-8")
    )[0]["name"] == "电脑二"


def test_independent_series_entities_merge_without_conflict(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    first = _runtime(tmp_path, library, "first")
    second = _runtime(tmp_path, library, "second")
    initial = [
        {"id": "series-a", "name": "A"},
        {"id": "series-b", "name": "B"},
    ]
    for runtime in (first, second):
        runtime.user_data.mkdir(parents=True)
        (runtime.user_data / "series.json").write_text(
            json.dumps(initial, ensure_ascii=False), encoding="utf-8"
        )
        SharedSettings(runtime).seed_legacy()
        SharedSettings(runtime).capture()
    SharedSettings(second).apply()

    (settings_dir(first) / "series.json").write_text(
        json.dumps([{"id": "series-a", "name": "A1"}, {"id": "series-b", "name": "B"}], ensure_ascii=False),
        encoding="utf-8",
    )
    assert not SharedSettings(first).capture()["conflicts"]
    (settings_dir(second) / "series.json").write_text(
        json.dumps([{"id": "series-a", "name": "A"}, {"id": "series-b", "name": "B2"}], ensure_ascii=False),
        encoding="utf-8",
    )
    result = SharedSettings(second).capture()
    assert result["captured"] == 1
    applied = SharedSettings(first).apply()
    assert not applied["conflicts"]
    merged = json.loads((settings_dir(first) / "series.json").read_text(encoding="utf-8"))
    assert {item["name"] for item in merged} == {"A1", "B2"}


def test_used_reference_is_not_restored_to_available_after_sync(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    first = _runtime(tmp_path, library, "first")
    (first.user_data / "reference_library").mkdir(parents=True)
    (first.user_data / "reference_library" / "ref.png").write_bytes(b"same-image")
    SharedSettings(first).seed_legacy()
    SharedSettings(first).capture()
    available = settings_dir(first) / "reference_library" / "ref.png"
    used_dir = settings_dir(first) / "reference_library" / "_used_20260908"
    used_dir.mkdir()
    available.rename(used_dir / "ref.png")
    SharedSettings(first).capture()

    second = _runtime(tmp_path, library, "second")
    SharedSettings(second).apply()
    assert not (settings_dir(second) / "reference_library" / "ref.png").exists()
    assert (settings_dir(second) / "reference_library" / "_used_20260908" / "ref.png").exists()


def test_removed_prompt_and_series_entities_create_tombstones_and_apply(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    first = _runtime(tmp_path, library, "first")
    first.user_data.mkdir(parents=True)
    (first.user_data / "series.json").write_text(
        json.dumps([{"id": "keep", "name": "保留"}, {"id": "remove", "name": "删除"}],
                   ensure_ascii=False), encoding="utf-8")
    (first.user_data / "prompts").mkdir()
    (first.user_data / "prompts" / "remove.json").write_text(
        json.dumps({"id": "remove", "name": "删除方案"}, ensure_ascii=False),
        encoding="utf-8")
    SharedSettings(first).seed_legacy()
    assert SharedSettings(first).capture()["captured"] >= 3

    second = _runtime(tmp_path, library, "second")
    SharedSettings(second).apply()
    settings = settings_dir(first)
    (settings / "series.json").write_text(
        json.dumps([{"id": "keep", "name": "保留"}], ensure_ascii=False),
        encoding="utf-8")
    (settings / "prompts" / "remove.json").unlink()
    capture = SharedSettings(first).capture()
    assert capture["tombstones"]

    deleted = [w for w in library.list_works(first.account_id)
               if w["state"] == "deleted"]
    assert {w["revision"]["metadata"]["setting_type"] for w in deleted} >= {"series", "prompt"}

    applied = SharedSettings(second).apply()
    assert not applied["conflicts"]
    assert json.loads((settings_dir(second) / "series.json").read_text(encoding="utf-8")) == [
        {"id": "keep", "name": "保留"}
    ]
    assert not (settings_dir(second) / "prompts" / "remove.json").exists()


def test_removed_reference_is_not_tombstoned_or_deleted_on_peer(tmp_path):
    library = ResourceLibrary(tmp_path / "shared", create=True)
    first = _runtime(tmp_path, library, "first")
    reference = first.user_data / "reference_library"
    reference.mkdir(parents=True)
    (reference / "keep.png").write_bytes(b"reference")
    SharedSettings(first).seed_legacy()
    SharedSettings(first).capture()

    second = _runtime(tmp_path, library, "second")
    SharedSettings(second).apply()
    (settings_dir(first) / "reference_library" / "keep.png").unlink()
    result = SharedSettings(first).capture()
    assert not result["tombstones"]
    assert not any(w["state"] == "deleted" and
                   w["revision"]["metadata"].get("setting_type") == "reference"
                   for w in library.list_works(first.account_id))
    SharedSettings(second).apply()
    assert (settings_dir(second) / "reference_library" / "keep.png").exists()
