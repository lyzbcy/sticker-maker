import json
import time
from pathlib import Path
import pytest

from sticker_engine.library.catalog import ResourceLibrary


def _raw(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_write_revision_invalidates_per_work_analysis_cache(tmp_path):
    """2026-09-10 性能根修配套：write_revision 后同一实例必须立刻看到新头。

    缓存以修订目录 mtime 为戳，写入路径显式失效——若失效缺失，引擎
    长会话里 resolve/capture 之后 read_work 仍是旧状态（静默数据旧读）。
    """
    library = ResourceLibrary(tmp_path / "library", create=True)
    resource = library.put_file(_raw(tmp_path, "a.png", b"a"))
    r1 = library.write_revision("acc", "work", {"v": 1}, {"a.png": resource})
    assert library.read_work("acc", "work")["revision"]["revision_id"] == r1["revision_id"]

    r2 = library.write_revision("acc", "work", {"v": 2}, {"a.png": resource},
                                parents=[r1["revision_id"]])
    work = library.read_work("acc", "work")
    assert work["revision"]["revision_id"] == r2["revision_id"]
    assert [h["revision_id"] for h in work["heads"]] == [r2["revision_id"]]


def test_external_revision_file_lands_via_directory_mtime(tmp_path):
    """Syncthing/他机落盘新修订（不经 write_revision）也要被感知：目录
    mtime 变化即缓存失效。"""
    library = ResourceLibrary(tmp_path / "library", create=True)
    resource = library.put_file(_raw(tmp_path, "a.png", b"a"))
    r1 = library.write_revision("acc", "work", {"v": 1}, {"a.png": resource})
    assert library.read_work("acc", "work")["state"] == "available"

    # 从第二个实例（模拟对端）写入同一库，再回到第一实例读取
    peer = ResourceLibrary(tmp_path / "library")
    peer.write_revision("acc", "work", {"v": 2}, {"a.png": resource},
                        parents=[r1["revision_id"]])
    # mtime 粒度保护：确保目录时间戳前进
    time.sleep(0.02)
    work = library.read_work("acc", "work")
    assert len(work["heads"]) == 1
    assert work["revision"]["metadata"]["v"] == 2


def test_disk_cache_survives_new_instance_and_invalidates_on_write(tmp_path):
    """盘缓存（2026-09-11）：新实例命中秒读；write_revision 后条目失效。"""
    import os
    lib = ResourceLibrary(tmp_path / "library", create=True)
    resource = lib.put_file(_raw(tmp_path, "a.png", b"a"))
    r1 = lib.write_revision("acc", "work", {"v": 1}, {"a.png": resource})
    # 新建作品的首次解析不进缓存（目录刚建无 mtime 戳）；二次读
    # （read_work/list_works——真实流程必触发）才落盘
    lib.read_work("acc", "work")
    lib.save_disk_cache()
    p = lib._disk_cache_path()
    assert p is not None and p.is_file(), "盘缓存文件应已落盘"

    # 新实例（模拟引擎重启）：读同一作品应命中盘缓存（不重解析）
    lib2 = ResourceLibrary(tmp_path / "library")
    assert lib2.read_work("acc", "work")["state"] == "available"

    # 写入新修订：盘缓存条目必须失效，新实例立刻看到新头
    lib2.write_revision("acc", "work", {"v": 2}, {"a.png": resource},
                        parents=[r1["revision_id"]])
    lib3 = ResourceLibrary(tmp_path / "library")
    w = lib3.read_work("acc", "work")
    assert (w["revision"] or {}).get("metadata", {}).get("v") == 2


@pytest.mark.parametrize('platform,segments', [
    ('darwin', ('Library', 'Application Support', 'StickerEngine')),
    ('linux', ('.local', 'share', 'StickerEngine')),
])
def test_disk_cache_without_windows_appdata_uses_platform_directory(tmp_path, monkeypatch, platform, segments):
    import os
    from sticker_engine.config import paths
    home = tmp_path / 'private' / 'var' / 'fixture-home'
    monkeypatch.delenv('APPDATA', raising=False)
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    monkeypatch.delenv('STICKER_ENGINE_USER_DATA', raising=False)
    monkeypatch.setattr(paths, 'current_platform', lambda: platform)
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(home / p[2:]) if p.startswith('~/') else str(home))
    lib = ResourceLibrary(tmp_path / 'library', create=True)
    resource = lib.put_file(_raw(tmp_path, 'platform.png', b'platform'))
    lib.write_revision('acc', 'work', {'v': 1}, {'a.png': resource})
    lib.read_work('acc', 'work'); lib.save_disk_cache()
    cache = lib._disk_cache_path()
    assert cache.parent == home.joinpath(*segments, 'catalog_cache')
    assert cache.is_file()
    assert ResourceLibrary(tmp_path / 'library').read_work('acc', 'work')['state'] == 'available'


def test_disk_cache_honors_isolated_device_override(tmp_path, monkeypatch):
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(tmp_path / 'isolated-device'))
    library = ResourceLibrary(tmp_path / 'library', create=True)
    assert library._disk_cache_path().parent == tmp_path / 'isolated-device' / 'catalog_cache'
