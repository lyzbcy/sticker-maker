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
MAX_PAGES = 40          # 防失控上限（全量翻页，80+ 作品约 8 页，40 富余）
_UI_BUTTON_WORDS = {"创建形象"}   # 列表页头部的 UI 按钮（非作品行，回归发现）
_STALL_ROWS = 20        # 连续 N 行已上架/下架 → 停止翻页（用户策略：翻到最深的活跃单为止）
# 状态词按精确匹配顺序排：否定词在前（"审核通过"是"审核未通过"的子串场景
# 由关键词表+先判长词避免）。2026-09-01 事故：缺"审核通过"导致过审单在
# 列表解析时被当非数据行跳过，本地状态永远停在旧"待审核"
_STATUS_WORDS = ("未通过审核", "审核未通过", "审核通过", "已上架",
                 "待审核", "已保存", "已下架")


@dataclass
class PlatformRow:
    """平台作品列表的一行。"""
    name: str
    status: str = ""
    downloads: str = "-"
    sends: str = "-"
    tips: str = "-"
    updated: str = ""
    reject_reason: str = ""   # 未通过审核时：详情页→未通过审核→表情驳回理由
    reject_stage: str = ""    # 诊断：抓取失败死在哪一步（locate/wait_btn/…）


def _extract_reason(text: str) -> str:
    """从理由页文本提取「表情驳回理由」之后的内容（页面结构：标题+组名+理由）。"""
    key = "表情驳回理由"
    i = text.find(key)
    if i < 0:
        return ""
    seg = text[i + len(key):].strip()
    # 截掉可能的页尾操作按钮文字
    for stop in ("重新提交", "返回列表", "返回管理", "常见问题", "公告"):
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
    return seg.strip()[:500]


def _fetch_reject_reason_for_row(page, row: "PlatformRow") -> str:
    """对一个「未通过审核」行抓驳回理由（SOP：详情→未通过审核→表情驳回理由）。

    流程（2026-08-29 实测）：管理页行内「详情」→ 详情页（慢，等 6s+）→
    点唯一的「未通过审核」→ 跳转理由页 → 提取文本 → go_back 回列表。
    任何一步失败返回空串（不阻断整页同步）。

    坑（2026-08-29 真机回归）：只有真点进详情才 go_back（否则回退过头，
    后续行的定位全错位——首行成功中间全空的根因）；go_back 后要等列表
    真正恢复（出现「详情」字样）再返回。
    """
    target = normalize_name(row.name)
    entered = False
    stage = "init"

    def _locate_and_click() -> bool:
        """找目标行的「详情」并点入（翻页查找——2026-09-02：重提洗牌后
        目标行可能不在当前页，60 的理由抓取失败即此因）。"""
        for _pg in range(10):
            links = page.locator("a:has-text('详情'), td:has-text('详情')")
            for i in range(links.count()):
                el = links.nth(i)
                try:
                    in_tr = el.evaluate("e=>e.closest('tr')!==null")
                    row_txt = (el.locator("xpath=ancestor::tr[1]").inner_text(timeout=2000)
                               if in_tr else el.inner_text(timeout=2000))
                except Exception:
                    continue
                if target and target in normalize_name(row_txt):
                    el.click()
                    return True
            nb = page.locator("a:has-text('下一页')")
            if not nb.count():
                return False
            try:
                nb.first.click(timeout=3000)
            except Exception:   # noqa: BLE001
                return False
            page.wait_for_timeout(2000)
        return False

    try:
        stage = "locate"
        entered = _locate_and_click()
        if not entered:
            # go_back 后的列表 DOM 可能没恢复稳（行定位全空）——goto 重置列表再试
            # 一次（2026-08-29 真机：65 成功后 61-64 全在 go_back 后定位失败，
            # 但详情页的「未通过审核」入口其实一直都在）
            stage = "locate_retry"
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            entered = _locate_and_click()
        if not entered:
            return ""
        # 详情页打开慢（实测需等一会儿）
        stage = "detail_load"
        page.wait_for_timeout(6000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        # 等「未通过审核」按钮真正渲染出来（个别作品详情页慢，赌固定 sleep
        # 会输——2026-08-29 真机：62 就是慢了几秒导致抓空）
        stage = "wait_btn"
        try:
            page.wait_for_selector("text=未通过审核", timeout=20000, state="attached")
        except Exception:
            return ""   # 详情页没有该入口（如状态已变/模板不同），留空
        page.locator("text=未通过审核").first.click()
        stage = "wait_reason"
        try:
            page.wait_for_selector("text=表情驳回理由", timeout=20000, state="attached")
        except Exception:
            pass
        page.wait_for_timeout(1500)
        return _extract_reason(page.inner_text("body")) or ""
    except Exception as e:   # noqa: BLE001
        row.reject_stage = stage + ":" + type(e).__name__   # 诊断：死在哪一步
        return ""
    finally:
        if entered:
            try:
                page.go_back(wait_until="domcontentloaded", timeout=30000)
                # 等列表页真正恢复（2026-09-01 二次事故：旧判据"作品名+详情"
                # 在详情页也满足 → go_back 没回列表就继续跑，翻页/下一行定位
                # 全落空）。列表页独有标志 =「提交作品」按钮 + 目标专辑名。
                back_ok = False
                for _ in range(24):
                    page.wait_for_timeout(500)
                    try:
                        t = page.inner_text("body")
                        if row.name in t and "提交作品" in t:
                            back_ok = True
                            break
                    except Exception:
                        continue
                if not back_ok:
                    # 兜底：强制回列表（比停在错误页面强）
                    page.goto(HOME_URL, wait_until="domcontentloaded",
                              timeout=45000)
                    page.wait_for_timeout(4000)
            except Exception:
                pass


def normalize_name(name: str) -> str:
    """归一化：NFKC 折叠全角数字/字母 → 去所有非字母数字（中文保留）→ 小写。

    2026-09-01（评审）：全角"５７"是平台表单高频输入事故，不折叠会漏配；
    大小写折叠防平台 UI 展示名做大小写处理。
    """
    import unicodedata
    folded = unicodedata.normalize("NFKC", str(name or ""))
    return re.sub(r"[\W_]+", "", folded).lower()


def match_episode(row_name: str, candidates: List[dict]) -> Optional[dict]:
    """把平台行名匹配到本地 episode（candidates 含 album_name/name 键）。

    两轮匹配（2026-09-01 两轮修复 + 评审加固）：
    1. 第一轮：归一化后**完全相等**——全局扫描、顺序无关；系列编号名
       （周三涵做表情5/57）只有精确匹配才归属（57 平台行曾前缀抢走 5 的
       本地单，一个 bug 同时造成"5 挂未通过审核"+"历史弹全部未同步"）。
    2. 第二轮（截断容错）：平台把长名截断显示（episode_20260825_180912 →
       episode202608251）。守卫：**两侧都必须有数字尾**，且满足"相等 /
       短尾>=4 位且为长尾前缀（时间戳截断特征）"——单侧无尾一律拒绝
       （评审高危：基础专辑"周三涵做表情"曾会命中"周三涵做表情1"）。
       多个不同候选同时满足 → 不可分辨，拒配进 unmatched 人工处理
       （评审中危：同小时两个时间戳作品曾按目录序先到先得）。
    """
    rn = normalize_name(row_name)
    if not rn:
        return None
    # 第一轮：全局精确
    for c in candidates:
        for key in ("album_name", "name"):
            ln = normalize_name(c.get(key) or "")
            if ln and rn == ln:
                return c

    def _tail(raw) -> str:
        # 对归一化名取尾数字（原始名的下划线会把尾数字截成最后一段）
        m = re.search(r"(\d+)$", normalize_name(raw))
        return m.group(1) if m else ""

    rn_tail = _tail(row_name)
    if not rn_tail:
        return None   # 行名无数字尾：无截断语义可言，直接不配
    # 第二轮：截断容错（收集全部满足者）
    hits = []
    for c in candidates:
        for key in ("album_name", "name"):
            raw = c.get(key) or ""
            ln = normalize_name(raw)
            if not ln or not (ln.startswith(rn) or rn.startswith(ln)):
                continue
            lt = _tail(raw)
            if not lt:
                continue                     # 候选无数字尾：拒绝（基础专辑防误配）
            if rn_tail == lt:
                hits.append(c)
                break
            short, long_ = sorted([rn_tail, lt], key=len)
            if len(short) >= 4 and long_.startswith(short):
                hits.append(c)               # 时间戳截断特征
                break
    uniq = []
    for h in hits:
        if h not in uniq:
            uniq.append(h)
    return uniq[0] if len(uniq) == 1 else None


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
            # 分页扫描（2026-09-01 二次调整）：**全量翻页**——下载/发送/
            # 赞赏数据只有已上架单才有，一键更新必须全量带回；本地脚本不花
            # token，页数成本可接受。卡页签名检测保留（防假数据累计）。
            last_sig = ""   # 上一页整页签名（防"点击翻页没前进"的死循环）
            stall_pages = 0  # 连续相同签名页数（连续 2 次才判卡页）
            for page_no in range(1, MAX_PAGES + 1):
                page.wait_for_timeout(1200)
                rows = parse_rows_from_text(page.inner_text("body"))
                # 过滤幻影行（2026-09-01 回归发现：页头按钮"创建形象"被当成
                # 行名，混进 unmatched 列表显示为不存在的作品）
                rows = [r for r in rows if r.name not in _UI_BUTTON_WORDS]
                if rows:
                    # 卡页检测（2026-09-01 引入；2026-09-03 误杀事故：签名
                    # 只取第 3-5 行，作品重提导致排序洗牌时连续两页前 3 行
                    # 撞车被误判"未前进"，16 页只扫了 6 页漏掉 100 条。改为
                    # **整页全签名 + 连续 2 次相同**才判卡页）
                    sig = "|".join(r.name for r in rows)
                    if sig and sig == last_sig:
                        stall_pages += 1
                        if stall_pages >= 2:
                            say("连续两页内容完全相同（翻页失效），停止扫描")
                            break
                    else:
                        stall_pages = 0
                    last_sig = sig
                    all_rows.extend(rows)
                    pages = page_no
                    say(f"已读取第 {page_no} 页（累计 {len(all_rows)} 条作品）…")
                    # 未通过审核的行：就地进详情抓驳回理由（用户需要知道为什么被拒）
                    _seen_r = set()
                    rejects = []
                    for r in rows:
                        if "未通过" in r.status and "审核" in r.status:
                            key = normalize_name(r.name)
                            if key in _seen_r:
                                continue   # 平台同名重复行，省一次详情往返
                            _seen_r.add(key)
                            rejects.append(r)
                    if rejects:
                        # 恢复分页位置（2026-09-01 根因：进详情抓理由后 go_back，
                        # 平台列表是 SPA 路由——回到的是第 1 页且分页状态丢失。
                        # 不恢复的话：本页后面的行定位全失败、翻页从第 1 页
                        # 重来还被卡页检测误杀）。每次抓取前都确认在本页——
                        # 上一次 go_back 一样会丢位置）
                        page_sig_before = "|".join(r.name for r in rows[2:5])

                        def _restore_page_pos():
                            for _ in range(12):
                                try:
                                    cur = "|".join(
                                        r.name for r in
                                        parse_rows_from_text(
                                            page.inner_text("body"))[2:5])
                                except Exception:   # noqa: BLE001
                                    cur = None
                                if cur == page_sig_before:
                                    return True
                                nb = page.locator("a:has-text('下一页')")
                                if not nb.count():
                                    return False
                                try:
                                    nb.first.click(timeout=3000)
                                except Exception:   # noqa: BLE001
                                    return False
                                page.wait_for_timeout(1800)
                            return False

                        for r in rejects:
                            _restore_page_pos()
                            say(f"正在读取「{r.name}」的驳回理由…")
                            r.reject_reason = _fetch_reject_reason_for_row(page, r)
                            if r.reject_reason:
                                say(f"  驳回理由：{r.reject_reason[:60]}…")
                            else:
                                why = (r.reject_stage or "列表定位失败(已重试)" if not r.reject_stage else r.reject_stage)
                                say(f"  （{r.name} 未取到驳回理由：{why}）")
                        _restore_page_pos()   # 供后续翻页/卡页检测
                        page.wait_for_timeout(800)
                    # 全量策略：不再 stall 停页（数据全量带回）
                # 翻页（2026-09-01 引入重试；2026-09-03 事故：抓完驳回
                # 理由恢复位置后翻页点击全部落空——16 页只扫 6 页漏 100 条。
                # 升级：点击后**验证页签名真的变了**才算成功；5 次都失败
                # 则 goto 重置从头快进到下一页兜底）
                def _cur_sig():
                    try:
                        return "|".join(
                            r.name for r in
                            parse_rows_from_text(page.inner_text("body")))
                    except Exception:   # noqa: BLE001
                        return ""

                def _click_next():
                    nb = page.locator("a:has-text('下一页')")
                    if not nb.count():
                        return False
                    try:
                        nb.first.click(timeout=3000)
                        return True
                    except Exception:   # noqa: BLE001
                        return False

                clicked = False
                for _ in range(5):
                    if _click_next():
                        page.wait_for_timeout(2200)
                        if _cur_sig() not in ("", last_sig):
                            clicked = True
                            break
                    page.wait_for_timeout(1500)
                if not clicked:
                    # 兜底：重置回第 1 页快进到 page_no+1
                    try:
                        page.goto(HOME_URL, wait_until="domcontentloaded",
                                  timeout=45000)
                        page.wait_for_timeout(3500)
                        for _ in range(page_no):
                            if not _click_next():
                                break
                            page.wait_for_timeout(1800)
                        if _cur_sig() not in ("", last_sig):
                            clicked = True
                    except Exception:   # noqa: BLE001
                        pass
                if not clicked:
                    break   # 真到最后一页（无下一页）或彻底翻不动
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
        if r.reject_reason:
            meta.platform_reject_reason = r.reject_reason
        if r.status in ("已上架", "待审核", "已保存"):
            meta.published = True
        save_meta(hit["dir"], meta)
        matched += 1
    say(f"同步完成：匹配 {matched} 个作品，平台未匹配 {len(unmatched)} 条")
    return {"matched": matched, "unmatched_platform": unmatched,
            "updated": matched, "pages": pages}
