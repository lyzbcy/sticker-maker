"""系列（series）与作品元数据（episode meta）管理。

命名体系（用户需求）：
- 用户定义系列，如「周思涵做表情系列」，起始编号 60；
- 同系列每个新作品自动取下一编号 → 专辑名「周思涵做表情 60」「周思涵做表情 61」…；
- 每个系列可配自己的介绍提示词（intro_prompt，留空用全局默认模板）；
- 每个系列可配角色素材映射（role_asset_map：角色名 → 固定横幅/封面/图标路径）。

存储位置：
- 系列：%APPDATA%/StickerEngine/series.json
- 作品元数据：每个 episode 目录下 meta.json（与产物放一起，随作品移动不丢）
"""
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .paths import resolve_paths, current_platform


def _series_file() -> Path:
    return resolve_paths(current_platform()).user_data / "series.json"


@dataclass
class Series:
    id: str
    name: str                        # 系列名，如「周思涵做表情」
    start_number: int = 1            # 起始编号（用户设定，如 60）
    next_number: int = 0             # 下一个要用的编号（0 = 未初始化，取 start_number）
    intro_prompt: str = ""           # 介绍生成提示词（空 = 用全局默认）
    role_asset_map: dict = field(default_factory=dict)
    # role_asset_map 结构：{"星星布丁": {"banner": "C:/.../b.png", "cover": "...", "icon": "..."}}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "start_number": self.start_number,
            "next_number": self.next_number or self.start_number,
            "intro_prompt": self.intro_prompt,
            "role_asset_map": self.role_asset_map,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Series":
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:8]),
            name=str(d.get("name") or "未命名系列"),
            start_number=int(d.get("start_number") or 1),
            next_number=int(d.get("next_number") or 0),
            intro_prompt=str(d.get("intro_prompt") or ""),
            role_asset_map=dict(d.get("role_asset_map") or {}),
        )

    def peek_next_number(self) -> int:
        """查看下一个编号（不动状态）。"""
        return self.next_number or self.start_number

    def take_number(self, occupied: set = None) -> int:
        """取走下一个编号（next_number 前进，需随后 save）。

        occupied：已占用的编号集合（可选）。提供时从 next_number 起找
        第一个未占用的号（2026-09-02 批量双重取号事故后补齐用——
        偶数号空缺时新单自动补上，不再留洞）。
        """
        n = self.peek_next_number()
        if occupied:
            while n in occupied:
                n += 1
        self.next_number = n + 1
        return n

    def album_name(self, number: int) -> str:
        # 平台规则：表情名称不能含空格（2026-08-29 抓到的驳回理由：
        # 「表情名称应避免出现空格，需要修改」——61/62/63 因此被拒）
        return f"{self.name}{number}"


def load_series() -> list:
    """读全部系列（文件不存在返回空列表）。"""
    path = _series_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Series.from_dict(item) for item in (data or [])]
    except (json.JSONDecodeError, OSError):
        return []


def save_series(series_list: list) -> None:
    path = _series_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([s.to_dict() for s in series_list], ensure_ascii=False, indent=2),
        encoding="utf-8")


def find_series(series_id: str) -> Optional[Series]:
    for s in load_series():
        if s.id == series_id:
            return s
    return None


def save_series_list_from_dicts(items: list) -> list:
    """前端整表保存（增删改一体）：[{id?, name, start_number, intro_prompt?, role_asset_map?}]。

    保留已有系列的 next_number（编号进度不因整表保存丢失）。
    """
    existing = {s.id: s for s in load_series()}
    result = []
    for item in items or []:
        sid = str(item.get("id") or "")
        prev = existing.get(sid)
        s = Series.from_dict(item)
        if prev is not None and sid:
            s.id = sid
            # 编号进度以已保存的为准（除非用户显式把 start_number 改大）
            if prev.next_number > s.start_number:
                s.next_number = prev.next_number
        result.append(s)
    save_series(result)
    return result


# ---------------- episode meta ----------------

@dataclass
class EpisodeMeta:
    series_id: Optional[str] = None
    series_name: str = ""
    number: Optional[int] = None
    album_name: str = ""             # 空 = 未命名（前端显示目录名）
    intro: str = ""
    published: bool = False
    published_at: str = ""
    created_at: str = ""
    # 素材设置：cover_mode = "auto"(默认拼贴) | "pick"(从本组选) | "custom"(自定义上传) | "role"(角色映射)
    cover_mode: str = "auto"
    cover_pick: int = 0              # pick 模式：本组第 N 张（0 起）
    cover_custom: str = ""           # custom 模式：文件路径
    banner_mode: str = "auto"
    banner_custom: str = ""
    icon_mode: str = "auto"
    icon_custom: str = ""
    # 平台状态（「一键更新」抓取回写，2026-08-27）
    platform_status: str = ""        # 已上架/待审核/未通过审核/已保存（空=本地未同步）
    platform_downloads: str = "-"    # 平台显示原样（可能是 "-"）
    platform_sends: str = "-"
    platform_tips: str = "-"         # 赞赏金额
    platform_updated_at: str = ""    # 最近一次同步时间
    # 未通过审核时的平台驳回理由（详情页→未通过审核→表情驳回理由，2026-08-29）
    platform_reject_reason: str = ""

    def to_dict(self) -> dict:
        return dict(
            series_id=self.series_id, series_name=self.series_name,
            number=self.number, album_name=self.album_name, intro=self.intro,
            published=self.published, published_at=self.published_at,
            created_at=self.created_at,
            cover_mode=self.cover_mode, cover_pick=self.cover_pick,
            cover_custom=self.cover_custom,
            banner_mode=self.banner_mode, banner_custom=self.banner_custom,
            icon_mode=self.icon_mode, icon_custom=self.icon_custom,
            platform_status=self.platform_status,
            platform_downloads=self.platform_downloads,
            platform_sends=self.platform_sends,
            platform_tips=self.platform_tips,
            platform_updated_at=self.platform_updated_at,
            platform_reject_reason=self.platform_reject_reason,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeMeta":
        fields = {f for f in cls.__dataclass_fields__}   # noqa: F841 - 过滤未知键
        safe = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**safe)


def meta_path(episode_dir: Path) -> Path:
    return Path(episode_dir) / "meta.json"


def load_meta(episode_dir: Path) -> EpisodeMeta:
    p = meta_path(episode_dir)
    if p.exists():
        try:
            return EpisodeMeta.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return EpisodeMeta()


def save_meta(episode_dir: Path, meta: EpisodeMeta) -> None:
    episode_dir = Path(episode_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)
    if not meta.created_at:
        meta.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    meta_path(episode_dir).write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def assign_to_series(episode_dir: Path, series: Series, occupied: set = None) -> EpisodeMeta:
    """把作品编入系列：取号 + 生成专辑名 + 写 meta。

    调用方负责随后 save_series（推进编号）。
    """
    meta = load_meta(episode_dir)
    meta.series_id = series.id
    meta.series_name = series.name
    meta.number = series.take_number(occupied=occupied)
    meta.album_name = series.album_name(meta.number)
    save_meta(episode_dir, meta)
    return meta


def rename_album(episode_dir: Path, album_name: str) -> EpisodeMeta:
    """手动改名（脱离系列编号的自由命名仍保留 series 归属）。"""
    meta = load_meta(episode_dir)
    meta.album_name = str(album_name or "").strip()[:30]   # 微信专辑名长度限制
    save_meta(episode_dir, meta)
    return meta


def mark_published(episode_dir: Path) -> EpisodeMeta:
    meta = load_meta(episode_dir)
    meta.published = True
    meta.published_at = time.strftime("%Y-%m-%d %H:%M:%S")
    save_meta(episode_dir, meta)
    return meta


def episode_sort_key(name: str):
    """episode 目录名排序键：episode_YYYYMMDD_HHMMSS 按时间；其他按名字。"""
    m = re.match(r"episode_(\d{8})_(\d{6})", name)
    return m.group(1) + m.group(2) if m else "0" * 14
