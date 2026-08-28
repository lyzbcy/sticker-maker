"""平台状态抓取（「一键更新」，2026-08-27）。

打开微信表情开放平台管理页，分页扫描全部作品行（名称/下载/发送/赞赏/状态/
最后更新），按专辑名匹配本地 episode，把平台状态写进 meta.json 本地库。

设计要点：
- 抓取逻辑写死（免 token）：复用发布浏览器的登录体系（storage_state 缓存 +
  密码自动重登），全程只读，不点任何提交类按钮。
- 名称匹配做归一化容错：平台列表会把长名截断/去下划线（如
  episode_20260825_180912 显示成 episode202608251），按「去非字母数字后
  前缀包含」匹配。
- 未匹配到的平台记录原样带回（脏数据/他人作品提示），不写本地。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

HOME_URL = ("https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/"
            "readtemplate?t=home/index")
MAX_PAGES = 15          # 防失控：7 页左右，15 绰绰有余
_STATUS_WORDS = ("已上架", "待审核", "未通过审核", "审核未通过", "已保存", "已下架")


@dataclass
class PlatformRow:
    """平台作品列表的一行。"""
    name: str
    status: str = ""
    downloads: str = "-"
    sends: str = "-"
    tips: str = "-"
    updated: str = ""


def normalize_name(name: str) -> str:
    """去掉所有非字母数字字符（含中文保留），用于前缀匹配。"""
    return re.sub(r"[\W_]+", "", str(name or ""))


def match_episode(row_name: str, candidates: List[dict]) -> Optional[dict]:
    """把平台行名匹配到本地 episode（candidates 含 album_name/name 键）。

    匹配规则（按优先级）：
    1. 归一化后完全相等
    2. 平台名（可能被截断）是本地名归一化形式的前缀，或互为前缀
    """
    rn = normalize_name(row_name)
    if not rn:
        return None
    for c in candidates:
        for key in ("album_name", "name"):
            ln = normalize_name(c.get(key) or "")
            if not ln:
                continue
            if rn == ln or ln.startswith(rn) or rn.startswith(ln):
                return c
    return None


def parse_rows_from_text(text: str) -> List[PlatformRow]:
    """从管理页 inner_text 解析作品行（DOM 表格结构不稳，文本行稳定）。

    形如：
        周三涵做表情 63
        -	-	-	待审核	原创	2026-08-27	详情
    """
    rows: List[PlatformRow] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        name_line = lines[i]
        # 下一行含状态词 + 至少 3 个制表/数据段才算数据行
        if i + 1 < len(lines):
            data_line = lines[i + 1]
            status = next((w for w in _STATUS_WORDS if w in data_line), "")
            if status:
                segs = [s.strip() for s in re.split(r"[\t]+", data_line) if s.strip()]
                # segs 通常是 [下载, 发送, 赞赏, 状态, 原创, 日期, 详情]
                nums = [s for s in segs if s in ("-",) or re.match(r"^[\d.,万]+$", s)]
                date = next((s for s in segs if re.match(r"\d{4}-\d{2}-\d{2}", s)), "")
                rows.append(PlatformRow(
                    name=name_line, status=status,
                    downloads=nums[0] if nums else "-",
                    sends=nums[1] if len(nums) > 1 else "-",
                    tips=nums[2] if len(nums) > 2 else "-",
                    updated=date))
                i += 2
                continue
        i += 1
    return rows


def sync_status(engine, on_status: Optional[Callable[[str], None]] = None
                ) -> dict:
    """扫描平台作品列表并回写本地 meta。

    返回 ``{matched, unmatched_platform, updated, pages}``。
    engine：StickerEngine（用它的 config.paths.output_root 找本地作品）。
    on_status：进度回调（喂给活动日志）。
    """
    def say(msg: str) -> None:
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    from .config import PublishConfig
    from .browser import BrowserSession
    from playwright.sync_api import sync_playwright
    from ..config.series import load_meta, save_meta

    root = Path(engine.config.paths.output_root)
    locals_ = []
    for ep_dir in sorted(root.iterdir()) if root.exists() else []:
        if ep_dir.is_dir() and ep_dir.name.startswith("episode"):
            meta = load_meta(ep_dir)
            locals_.append({"dir": ep_dir, "meta": meta,
                            "album_name": meta.album_name or ep_dir.name,
                            "name": ep_dir.name})

    say("正在启动浏览器读取平台作品列表…")
    cfg = PublishConfig()
    all_rows: List[PlatformRow] = []
    pages = 0
    with sync_playwright() as p:
        b = BrowserSession(cfg, playwright=p)
        page = b.start(headless=False)
        try:
            if not b.ensure_login(page, on_status=say):
                return {"error": f"登录失败：{b.last_login_error or '未知原因'}",
                        "matched": 0, "unmatched_platform": [], "pages": 0}
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            # 分页扫描：点「下一页」直到不可点或达上限
            for page_no in range(1, MAX_PAGES + 1):
                page.wait_for_timeout(1200)
                rows = parse_rows_from_text(page.inner_text("body"))
                if rows:
                    all_rows.extend(rows)
                    pages = page_no
                    say(f"已读取第 {page_no} 页（累计 {len(all_rows)} 条作品）…")
                next_btn = page.locator("a:has-text('下一页')")
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                try:
                    next_btn.first.click()
                except Exception:
                    break
        finally:
            b.close()

    # 去重（同一专辑可能翻页重复抓到）
    seen = {}
    for r in all_rows:
        seen[normalize_name(r.name)] = r
    all_rows = list(seen.values())

    # 匹配回写
    matched = 0
    unmatched: List[dict] = []
    used_dirs = set()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for r in all_rows:
        hit = match_episode(r.name, locals_)
        if hit is None or str(hit["dir"]) in used_dirs:
            unmatched.append({"name": r.name, "status": r.status, "updated": r.updated})
            continue
        used_dirs.add(str(hit["dir"]))
        meta = hit["meta"]
        meta.platform_status = r.status
        meta.platform_downloads = r.downloads
        meta.platform_sends = r.sends
        meta.platform_tips = r.tips
        meta.platform_updated_at = now
        if r.status in ("已上架", "待审核", "已保存"):
            meta.published = True
        save_meta(hit["dir"], meta)
        matched += 1
    say(f"同步完成：匹配 {matched} 个作品，平台未匹配 {len(unmatched)} 条")
    return {"matched": matched, "unmatched_platform": unmatched,
            "updated": matched, "pages": pages}
