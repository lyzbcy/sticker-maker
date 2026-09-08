import hashlib
import os
from pathlib import Path

import pytest

from sticker_engine.library import deletion


def _digest(path: Path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def test_safe_unlink_verified_removes_the_verified_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = root / "nested" / "source.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"verified")
    digest, size = _digest(source)

    deletion.safe_unlink_verified(source, root, digest, size)

    assert not source.exists()


def test_safe_unlink_verified_keeps_source_when_content_changes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = root / "source.bin"
    root.mkdir()
    source.write_bytes(b"original")
    digest, size = _digest(source)
    source.write_bytes(b"changed")

    with pytest.raises((OSError, ValueError)):
        deletion.safe_unlink_verified(source, root, digest, size)

    assert source.read_bytes() == b"changed"


def test_safe_unlink_verified_keeps_a_replacement_after_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    source = root / "source.bin"
    root.mkdir()
    source.write_bytes(b"original")
    digest, size = _digest(source)
    original_hash = deletion._hash_posix_fd

    def hash_then_replace(fd):
        result = original_hash(fd)
        source.unlink()
        source.write_bytes(b"replacement")
        return result

    monkeypatch.setattr(deletion, "_hash_posix_fd", hash_then_replace)
    with pytest.raises((OSError, ValueError)):
        deletion.safe_unlink_verified(source, root, digest, size)

    assert source.read_bytes() == b"replacement"


def test_safe_unlink_verified_rejects_a_leaf_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.bin"
    source = root / "source.bin"
    root.mkdir()
    outside.write_bytes(b"outside")
    try:
        source.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    digest, size = _digest(outside)
    with pytest.raises((OSError, ValueError)):
        deletion.safe_unlink_verified(source, root, digest, size)

    assert source.is_symlink()
    assert outside.read_bytes() == b"outside"


def test_safe_unlink_verified_rejects_a_replaced_parent_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    parent = root / "nested"
    moved_parent = tmp_path / "moved-nested"
    outside = tmp_path / "outside"
    source = parent / "source.bin"
    root.mkdir()
    parent.mkdir()
    outside.mkdir()
    source.write_bytes(b"verified")
    outside_source = outside / "source.bin"
    outside_source.write_bytes(b"outside")
    digest, size = _digest(source)
    original_hash = deletion._hash_posix_fd

    def hash_then_replace_parent(fd):
        result = original_hash(fd)
        try:
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are unavailable")
        return result

    monkeypatch.setattr(deletion, "_hash_posix_fd", hash_then_replace_parent)

    with pytest.raises((OSError, ValueError)):
        deletion.safe_unlink_verified(source, root, digest, size)

    assert (moved_parent / "source.bin").read_bytes() == b"verified"
    assert outside_source.read_bytes() == b"outside"


def test_windows_handle_deletion_implementation_is_kept_for_static_review() -> None:
    source = Path(deletion.__file__).read_text(encoding="utf-8")
    if os.name == "nt":
        pytest.skip("real Windows execution is not covered in this environment")
    for symbol in (
        "CreateFileW",
        "FILE_FLAG_OPEN_REPARSE_POINT",
        "GetFinalPathNameByHandleW",
        "SetFileInformationByHandle",
    ):
        assert symbol in source
