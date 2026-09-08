"""Verified source-file deletion with directory/handle based confinement.

The callers of :func:`safe_unlink_verified` have already verified the
destination copy.  This module performs the last source-side verification and
deletion without resolving a path again at the point where an ancestor could
have been replaced by a symbolic link.

POSIX uses directory file descriptors and ``O_NOFOLLOW`` for every component,
then isolates the verified directory entry under a private temporary name
before removing it.  Windows uses a source handle opened with
``FILE_FLAG_OPEN_REPARSE_POINT`` and deletes that handle with
``SetFileInformationByHandle``; a later path replacement therefore cannot
redirect deletion to another file.
"""

from __future__ import annotations

import ctypes
import hashlib
import operator
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_CHUNK_SIZE = 1024 * 1024


def _expected_values(expected_hash: str, expected_size: int) -> Tuple[str, int]:
    if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
        raise ValueError("expected_hash must be a SHA-256 hexadecimal digest")
    try:
        size = operator.index(expected_size)
    except TypeError as exc:
        raise TypeError("expected_size must be an integer") from exc
    if size < 0:
        raise ValueError("expected_size must not be negative")
    return expected_hash.casefold(), int(size)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        int(getattr(left, "st_dev", 0)) == int(getattr(right, "st_dev", 0))
        and int(getattr(left, "st_ino", 0)) == int(getattr(right, "st_ino", 0))
    )


def _verify_digest(actual_hash: str, actual_size: int, expected_hash: str, expected_size: int) -> None:
    if actual_size != expected_size or actual_hash.casefold() != expected_hash:
        raise ValueError("source changed or does not match the expected digest")


def _absolute_path(path: Path) -> str:
    value = os.fspath(Path(path))
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    return os.path.normpath(os.path.abspath(value))


def _posix_relative_parts(source: Path, root: Path) -> Tuple[str, str, Tuple[str, ...]]:
    source_abs = _absolute_path(source)
    root_abs = _absolute_path(root)
    try:
        relative = os.path.relpath(source_abs, root_abs)
    except ValueError as exc:
        raise ValueError("source and root are on different path domains") from exc
    if relative == "." or relative.startswith(".." + os.sep) or relative == "..":
        raise ValueError("source is outside root")
    parts = tuple(part for part in relative.split(os.sep) if part not in ("", "."))
    if not parts or any(part == ".." for part in parts):
        raise ValueError("source is outside root")
    return source_abs, root_abs, parts


def _posix_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise OSError("O_NOFOLLOW is required for verified deletion")
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | nofollow
    )


@contextmanager
def _open_posix_parent(root_abs: str, relative_parts: Sequence[str]) -> Iterator[Tuple[int, str, List[int]]]:
    """Open root and source-parent directories without following links.

    Every opened directory remains live until the caller has completed the
    rename/unlink.  Operations on the final parent descriptor consequently
    continue to address the originally verified directory even if its name is
    replaced in the meantime.
    """

    flags = _posix_directory_flags()
    fds: List[int] = []
    current: Optional[int] = None
    try:
        # The root is absolute, so opening '/' gives us a stable starting
        # descriptor for checking every component of the root path itself.
        current = os.open(os.sep, flags)
        fds.append(current)
        root_parts = tuple(part for part in root_abs.split(os.sep) if part)
        for component in root_parts:
            current = os.open(component, flags, dir_fd=current)
            fds.append(current)
        root_stat = os.fstat(current)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("root is not a directory")

        for component in relative_parts[:-1]:
            current = os.open(component, flags, dir_fd=current)
            fds.append(current)
        yield current, relative_parts[-1], fds
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _hash_posix_fd(fd: int) -> Tuple[str, int, os.stat_result]:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("source is not a regular file")
    try:
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError:
        # A regular file descriptor should be seekable.  Preserve the native
        # error when an unusual filesystem violates that assumption.
        raise
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(fd, _CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    after = os.fstat(fd)
    if not _same_identity(before, after) or int(before.st_size) != int(after.st_size):
        raise ValueError("source changed while being read")
    return digest.hexdigest(), size, after


def _revalidate_posix_parent(root_abs: str, relative_parts: Sequence[str], held_fds: Sequence[int]) -> None:
    """Ensure every named directory still denotes the held directory fd."""

    with _open_posix_parent(root_abs, relative_parts) as (_parent_fd, _leaf, current_fds):
        if len(current_fds) != len(held_fds):
            raise ValueError("root or source parent changed during deletion")
        for held_fd, current_fd in zip(held_fds, current_fds):
            if not _same_identity(os.fstat(held_fd), os.fstat(current_fd)):
                raise ValueError("root or source parent changed during deletion")


def _reserve_posix_temp(parent_fd: int, leaf: str) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    for _ in range(32):
        name = ".{}.delete-{}.tmp".format(leaf, uuid.uuid4().hex)
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            os.close(fd)
        except BaseException as exc:
            try:
                os.unlink(name, dir_fd=parent_fd)
            except BaseException as cleanup_exc:
                raise cleanup_exc from exc
            raise
        return name
    raise FileExistsError("could not reserve a temporary deletion name")


def _restore_posix_temp(parent_fd: int, temporary: str, leaf: str) -> None:
    """Restore a quarantined entry without overwriting a new source entry."""

    try:
        os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        os.rename(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        return
    raise ValueError("source path changed during deletion; temporary file was retained")


def _safe_unlink_posix(source: Path, root: Path, expected_hash: str, expected_size: int) -> None:
    expected_hash, expected_size = _expected_values(expected_hash, expected_size)
    _source_abs, root_abs, relative_parts = _posix_relative_parts(source, root)
    leaf_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if not getattr(os, "O_NOFOLLOW", 0):
        raise OSError("O_NOFOLLOW is required for verified deletion")

    with _open_posix_parent(root_abs, relative_parts) as (parent_fd, leaf, held_fds):
        source_fd = os.open(leaf, leaf_flags, dir_fd=parent_fd)
        try:
            initial = os.fstat(source_fd)
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError("source is not a regular file")
            actual_hash, actual_size, stable = _hash_posix_fd(source_fd)
            _verify_digest(actual_hash, actual_size, expected_hash, expected_size)

            # A caller may have replaced an ancestor while the file was being
            # hashed.  Re-open the named chain with O_NOFOLLOW and compare it
            # with the descriptors held for the deletion operation.
            _revalidate_posix_parent(root_abs, relative_parts, held_fds)

            # Confirm the name still denotes the descriptor we hashed.  The
            # later quarantine rename and the final unlink both use parent_fd,
            # never a re-resolved source path.
            named = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(named.st_mode) or not _same_identity(named, stable):
                raise ValueError("source path changed during verification")

            temporary = _reserve_posix_temp(parent_fd, leaf)
            quarantined = False
            try:
                os.rename(leaf, temporary, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                quarantined = True

                _revalidate_posix_parent(root_abs, relative_parts, held_fds)

                # A replacement between the name check and rename is moved to
                # the temporary name instead of being deleted.  Verify the
                # quarantined entry before touching it.
                temporary_fd = os.open(temporary, leaf_flags, dir_fd=parent_fd)
                try:
                    quarantined_stat = os.fstat(temporary_fd)
                    quarantined_hash, quarantined_size, _quarantined_after = _hash_posix_fd(
                        temporary_fd
                    )
                finally:
                    os.close(temporary_fd)
                if not _same_identity(quarantined_stat, stable):
                    raise ValueError("source path was replaced during deletion")
                _verify_digest(
                    quarantined_hash,
                    quarantined_size,
                    expected_hash,
                    expected_size,
                )
                current_temporary = os.stat(
                    temporary, dir_fd=parent_fd, follow_symlinks=False
                )
                if not _same_identity(current_temporary, stable):
                    raise ValueError("temporary deletion entry was replaced")

                _revalidate_posix_parent(root_abs, relative_parts, held_fds)

                os.unlink(temporary, dir_fd=parent_fd)
                quarantined = False
            except BaseException as exc:
                if quarantined:
                    try:
                        _restore_posix_temp(parent_fd, temporary, leaf)
                    except BaseException as restore_exc:
                        raise restore_exc from exc
                raise
        finally:
            os.close(source_fd)


if os.name == "nt":
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _GENERIC_READ = 0x80000000
    _DELETE = 0x00010000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_BEGIN = 0
    _FILE_BASIC_INFO_CLASS = 0
    _FILE_STANDARD_INFO_CLASS = 1
    _FILE_DISPOSITION_INFO_CLASS = 4

    class _FileBasicInfo(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
        ]

    class _FileStandardInfo(ctypes.Structure):
        _fields_ = [
            ("AllocationSize", ctypes.c_longlong),
            ("EndOfFile", ctypes.c_longlong),
            ("NumberOfLinks", wintypes.DWORD),
            ("DeletePending", wintypes.BOOLEAN),
            ("Directory", wintypes.BOOLEAN),
        ]

    class _FileDispositionInfo(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOLEAN)]

    _KERNEL32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _KERNEL32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _KERNEL32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_wchar_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _KERNEL32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _KERNEL32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    ]
    _KERNEL32.SetFilePointerEx.restype = wintypes.BOOL
    _KERNEL32.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    _KERNEL32.ReadFile.restype = wintypes.BOOL
    _KERNEL32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _KERNEL32.SetFileInformationByHandle.restype = wintypes.BOOL

    def _windows_error() -> OSError:
        return ctypes.WinError(ctypes.get_last_error())

    def _windows_open(path: str, *, directory: bool, delete: bool = False):
        desired = _GENERIC_READ | (_DELETE if delete else 0)
        flags = _FILE_FLAG_OPEN_REPARSE_POINT
        if directory:
            flags |= _FILE_FLAG_BACKUP_SEMANTICS
        # Keep verified handles stable while hashing and deleting.  A source
        # handle shares reads only, so a concurrent writer/rename cannot alter
        # the object after verification.  Directory handles share writes for
        # normal child operations but deliberately do not share delete, which
        # prevents an ancestor rename/reparse swap while they are held.
        share_mode = _FILE_SHARE_READ
        if directory:
            share_mode |= _FILE_SHARE_WRITE
        handle = _KERNEL32.CreateFileW(
            path,
            desired,
            share_mode,
            None,
            _OPEN_EXISTING,
            flags,
            None,
        )
        if handle is None or getattr(handle, "value", handle) == _INVALID_HANDLE_VALUE:
            raise _windows_error()
        return handle

    def _windows_close(handle) -> None:
        if not _KERNEL32.CloseHandle(handle):
            raise _windows_error()

    def _windows_info(handle, info_class: int, info_type):
        info = info_type()
        if not _KERNEL32.GetFileInformationByHandleEx(
            handle, info_class, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise _windows_error()
        return info

    def _windows_final_path(handle) -> str:
        capacity = 512
        while True:
            buffer = ctypes.create_unicode_buffer(capacity)
            length = _KERNEL32.GetFinalPathNameByHandleW(handle, buffer, capacity, 0)
            if not length:
                raise _windows_error()
            if length < capacity - 1:
                return buffer.value
            capacity = int(length) + 1

    def _windows_strip_prefix(value: str) -> str:
        if value.startswith("\\\\?\\UNC\\"):
            return "\\\\" + value[8:]
        if value.startswith("\\\\?\\"):
            return value[4:]
        return value

    def _windows_within(path: str, root: str) -> bool:
        path = os.path.normcase(os.path.normpath(_windows_strip_prefix(path)))
        root = os.path.normcase(os.path.normpath(_windows_strip_prefix(root)))
        try:
            return path != root and os.path.commonpath((path, root)) == root
        except ValueError:
            return False

    def _windows_components(path: str) -> Iterator[str]:
        parsed = Path(path)
        current = Path(parsed.anchor)
        yield str(current)
        for part in parsed.parts[1:]:
            current = current / part
            yield str(current)

    def _windows_verify_directory_chain(root_abs: str, source_abs: str) -> List[object]:
        parent_abs = os.path.dirname(source_abs)
        paths = list(_windows_components(root_abs))
        root_norm = os.path.normcase(os.path.normpath(root_abs))
        for candidate in _windows_components(parent_abs):
            if os.path.normcase(os.path.normpath(candidate)) not in {
                os.path.normcase(os.path.normpath(item)) for item in paths
            }:
                paths.append(candidate)
        handles: List[object] = []
        try:
            for candidate in paths:
                handle = _windows_open(candidate, directory=True)
                handles.append(handle)
                info = _windows_info(handle, _FILE_BASIC_INFO_CLASS, _FileBasicInfo)
                if info.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ValueError("root or source parent is a reparse point")
            if not handles:
                raise ValueError("root is not a directory")
            root_info = _windows_info(handles[-1], _FILE_STANDARD_INFO_CLASS, _FileStandardInfo)
            if root_info.Directory == 0:
                raise ValueError("root is not a directory")
            return handles
        except BaseException:
            for handle in reversed(handles):
                _windows_close(handle)
            raise

    def _windows_hash(handle) -> Tuple[str, int]:
        if not _KERNEL32.SetFilePointerEx(
            handle, ctypes.c_longlong(0), None, _FILE_BEGIN
        ):
            raise _windows_error()
        digest = hashlib.sha256()
        buffer = ctypes.create_string_buffer(_CHUNK_SIZE)
        read_count = wintypes.DWORD()
        size = 0
        while True:
            if not _KERNEL32.ReadFile(
                handle, buffer, _CHUNK_SIZE, ctypes.byref(read_count), None
            ):
                raise _windows_error()
            if not read_count.value:
                break
            digest.update(ctypes.string_at(buffer, read_count.value))
            size += int(read_count.value)
        return digest.hexdigest(), size

    def _safe_unlink_windows(source: Path, root: Path, expected_hash: str, expected_size: int) -> None:
        expected_hash, expected_size = _expected_values(expected_hash, expected_size)
        source_abs = _absolute_path(source)
        root_abs = _absolute_path(root)
        if not _windows_within(source_abs, root_abs):
            raise ValueError("source is outside root")

        directory_handles = _windows_verify_directory_chain(root_abs, source_abs)
        source_handle = None
        try:
            root_final = _windows_final_path(directory_handles[-1])
            source_handle = _windows_open(source_abs, directory=False, delete=True)
            basic = _windows_info(source_handle, _FILE_BASIC_INFO_CLASS, _FileBasicInfo)
            standard = _windows_info(source_handle, _FILE_STANDARD_INFO_CLASS, _FileStandardInfo)
            if basic.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT or standard.Directory:
                raise ValueError("source is not a regular file")
            if not _windows_within(_windows_final_path(source_handle), root_final):
                raise ValueError("source path escaped root")
            actual_hash, actual_size = _windows_hash(source_handle)
            _verify_digest(actual_hash, actual_size, expected_hash, expected_size)
            # Re-check the handle after streaming the file.  The handle itself
            # remains the deletion authority if its directory entry is swapped.
            standard_after = _windows_info(
                source_handle, _FILE_STANDARD_INFO_CLASS, _FileStandardInfo
            )
            if int(standard_after.EndOfFile) != actual_size:
                raise ValueError("source changed while being read")
            second_hash, second_size = _windows_hash(source_handle)
            _verify_digest(second_hash, second_size, expected_hash, expected_size)
            if not _windows_within(_windows_final_path(source_handle), root_final):
                raise ValueError("source path escaped root")
            disposition = _FileDispositionInfo(1)
            if not _KERNEL32.SetFileInformationByHandle(
                source_handle,
                _FILE_DISPOSITION_INFO_CLASS,
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
            ):
                raise _windows_error()
        finally:
            if source_handle is not None:
                _windows_close(source_handle)
            for handle in reversed(directory_handles):
                _windows_close(handle)


def safe_unlink_verified(
    source: Path, root: Path, expected_hash: str, expected_size: int
) -> None:
    """Delete ``source`` only after confined, streaming verification.

    ``source`` must be a regular file below ``root`` and must match the
    expected SHA-256 digest and byte size.  Any verification or operating
    system failure raises and leaves the source entry in place.  The POSIX
    implementation uses a held parent descriptor and the Windows
    implementation deletes the verified source handle itself.
    """

    source = Path(source)
    root = Path(root)
    if os.name == "nt":
        _safe_unlink_windows(source, root, expected_hash, expected_size)
    else:
        _safe_unlink_posix(source, root, expected_hash, expected_size)


__all__ = ["safe_unlink_verified"]
