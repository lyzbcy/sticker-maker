"""Publisher: 单弹提交到微信表情开放平台（24 步）。

把 A 产出的 episode 一弹素材一键提交审核。24 步逻辑迁移自现有 publisher
skill（puppeteer 版 publish.js），用 playwright sync API 重写，选择器全部
走 :mod:`sticker_engine.publish.selectors` 的常量 S（平台改版只改那里）。

入口：
    Publisher(config, session).publish(episode_dir)

返回 ``{success, step, error, album_name?}``。失败时自动截图保现场。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import PublishConfig
from .browser import BrowserSession
from . import selectors as S


# ---------------------------------------------------------------------------
# episode 素材解析（纯文件操作，可独立单测，不需要 playwright）
# ---------------------------------------------------------------------------


def _find(p: Path) -> Optional[Path]:
    """存在则返回该路径，否则 None。"""
    return p if p.exists() else None


@dataclass
class EpisodeAssets:
    """从 episode 目录解析出的发布素材。

    stickers / meanings 按故事线顺序对齐（优先 ``meaning_map.json`` 的
    int key 1→N，否则按中文文件名排序）。
    """

    episode_dir: Path
    stickers: List[Path] = field(default_factory=list)
    meanings: List[str] = field(default_factory=list)
    album_name: str = ""
    intro: str = ""
    banner: Optional[Path] = None
    cover: Optional[Path] = None
    icon: Optional[Path] = None
    contains_laoyu: bool = False
    characters: list = field(default_factory=list)   # 本次制作角色（单/多角色选分类用）
    # episode 级赞赏图（S3 用本组角色生成，69 驳回整改：默认图与形象无关）
    tip_guide: Optional[Path] = None
    tip_thanks: Optional[Path] = None

    @classmethod
    def from_dir(cls, episode_dir: Path) -> "EpisodeAssets":
        episode_dir = Path(episode_dir)
        final = episode_dir / "最终版"

        # ---- 含义词排序：优先 meaning_map.json 的 key 顺序 ----
        meaning_map_path: Optional[Path] = None
        candidates = [
            episode_dir / "meaning_map.json",
            episode_dir / "原图" / "_meaning_map.json",
            episode_dir / "原图" / "meaning_map.json",
        ]
        for c in candidates:
            if c.exists():
                meaning_map_path = c
                break

        stickers: List[Path] = []
        meanings: List[str] = []
        if final.exists():
            if meaning_map_path is not None:
                try:
                    mm = json.loads(meaning_map_path.read_text(encoding="utf-8"))
                    # key 可能是 "1".."16" 或 int，按数字升序
                    sorted_keys = sorted(mm.keys(), key=lambda k: int(k))
                    final_pngs = {p.stem: p for p in final.glob("*.png")}
                    for k in sorted_keys:
                        meaning = mm[k]
                        # 文件名 == 含义词（A 产出约定）
                        hit = final_pngs.get(str(meaning))
                        if hit is None:
                            # 文件名可能带后缀，尝试包含匹配
                            hits = [p for s, p in final_pngs.items() if str(meaning) in s]
                            hit = hits[0] if hits else None
                        if hit is not None:
                            stickers.append(hit)
                            meanings.append(str(meaning))
                except (json.JSONDecodeError, ValueError):
                    # meaning_map 损坏 → 回退到文件名排序
                    meaning_map_path = None

            if not stickers:
                # 回退：按中文文件名排序
                for p in sorted(final.glob("*.png"), key=lambda x: x.stem):
                    stickers.append(p)
                    meanings.append(p.stem)

        # ---- 介绍.txt（截 80 字，平台限制）----
        intro = ""
        intro_path = episode_dir / "介绍.txt"
        if intro_path.exists():
            intro = intro_path.read_text(encoding="utf-8").strip()[:80]

        # ---- 角色卡：是否含捞鱼 + 角色列表 ----
        contains_laoyu = False
        characters = []
        char_path = episode_dir / "本次制作角色.md"
        if char_path.exists():
            char_text = char_path.read_text(encoding="utf-8")
            contains_laoyu = "含捞鱼：是" in char_text
            for line in char_text.splitlines():
                line = line.strip()
                if line.startswith("角色："):
                    characters = [c for c in line[len("角色："):].split("、") if c]
                    break

        # ---- 专辑名：优先 meta.json 的正式名（系列编号名），目录名只是兜底 ----
        # 2026-08-27 回归事故：这里原样用 episode_dir.name（时间戳），导致
        # 平台上出现「episode202608251 待审核」的错误名称提交——meta 里明明
        # 有「周三涵做表情 61」。cli 的发布前置校验只拦"没命名"，拦不住
        # "命名了但收集时没用上"。
        album_name = episode_dir.name
        meta_path = episode_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                named = str(meta.get("album_name") or "").strip()
                if named and not named.startswith("episode_"):
                    album_name = named
            except Exception:
                pass   # meta 损坏时退回目录名（前置校验会拦住时间戳名）

        return cls(
            episode_dir=episode_dir,
            stickers=stickers,
            meanings=meanings,
            album_name=album_name,
            intro=intro,
            banner=_find(episode_dir / "横幅" / "横幅.png"),
            cover=_find(episode_dir / "封面" / "封面.png"),
            icon=_find(episode_dir / "图标" / "图标.png"),
            contains_laoyu=contains_laoyu,
            characters=characters,
            tip_guide=_find(episode_dir / "赞赏图" / "赞赏引导图.png"),
            tip_thanks=_find(episode_dir / "赞赏图" / "赞赏致谢图.png"),
        )

    def validate(self) -> List[str]:
        """返回阻断性问题列表（空列表 = 可发布）。"""
        problems: List[str] = []
        if not self.stickers:
            problems.append("无表情图（最终版/ 为空）")
        if len(self.stickers) != len(self.meanings):
            problems.append("表情图与含义词数量不一致")
        return problems


# ---------------------------------------------------------------------------
# Publisher：24 步单弹提交
# ---------------------------------------------------------------------------


class Publisher:
    """单弹提交（24 步）。

    Parameters
    ----------
    config : PublishConfig
        固定配置 + 赞赏图路径 + 登录凭据。
    session : BrowserSession
        封装登录态持久化的 playwright 会话。

    Notes
    -----
    各 ``_step_*`` 方法都尽量容错（失败不立即抛），只有在最后提交前/提交后
    才整体校验。选择器全部来自 selectors.py 常量 S。
    """

    # 步骤方法名 → 中文名（warnings 展示用）
    _STEP_LABELS = {
        "_step_open_submit_form": "打开提交表单", "_step_upload_stickers": "上传表情图",
        "_step_fill_meanings": "填写含义词", "_step_fill_album_info": "填写专辑信息",
        "_step_fill_copyright": "填写版权信息", "_step_upload_assets": "上传横幅/封面/图标",
        "_upload_asset": "上传素材图",
        "_step_select_categories": "选择分类", "_step_select_price": "选择价格",
        "_step_tips": "配置赞赏", "_step_submit": "提交",
        "_upload_uploader_at": "上传宣传图", "_confirm_crop": "确认裁剪",
        "_select_role": "选择角色", "_upload_tip_images": "上传赞赏图",
        "_upload_tip_by_label": "上传赞赏图", "_upload_uploader_last": "上传赞赏图",
    }

    def __init__(self, config: PublishConfig, session: BrowserSession, progress=None,
                 vision=None):
        self.config = config
        self.session = session
        self.vision = vision   # 可选：含义词识图重填用（无则走 config 的 codex）
        # 可选进度回调 (step_name, message, percent)，桌面层用来直播发布过程
        self.progress = progress
        # 发布过程告警：哪个步骤的哪个字段没填上（不再静默吞掉）
        self.warnings = []

    def _warn(self, exc_or_msg) -> None:
        """记录步骤告警。自动定位调用者步骤名，转成人类可读描述。"""
        import sys
        step = sys._getframe(1).f_code.co_name
        label = self._STEP_LABELS.get(step, step)
        detail = f"{type(exc_or_msg).__name__}: {exc_or_msg}" if isinstance(exc_or_msg, Exception) else str(exc_or_msg)
        # Timeout 通常是元素找不到（页面改版/字段变化），翻译成人话
        if "Timeout" in type(exc_or_msg).__name__ if isinstance(exc_or_msg, Exception) else False:
            detail = "页面上找不到对应控件（可能改版）"
        msg = f"{label}未完成：{detail}"
        if msg not in self.warnings:
            self.warnings.append(msg)
        if self.progress:
            try:
                self.progress("warn", f"⚠ {msg}", 0.9)
            except Exception as e:  # noqa: BLE001
                self._warn(e)

    def _report(self, step: str, message: str, percent: float) -> None:
        if self.progress:
            try:
                self.progress(step, message, percent)
            except Exception:
                pass   # 进度上报失败不产生告警（避免递归）

    # ---- 主流程 ----

    def publish(self, episode_dir, headless: Optional[bool] = None, edit: bool = False,
                fix_fields=None) -> dict:
        """发布一弹。edit=True 走「编辑已驳回作品」入口（修改后重新提交审核）。

        fix_fields：编辑模式下**只改这些字段**（"album"/"stickers"/"icon"/
        "cover"/"tips"/"role"/"categories"），None=全量重走。精准修改来自
        驳回理由关键词（2026-08-29 用户 SOP：只改有问题的部分）。
        返回 ``{success, step, error?, album_name?}``。"""
        fields = set(fix_fields) if fix_fields else None
        assets = EpisodeAssets.from_dir(Path(episode_dir))

        # ---- 步骤前：本地校验，早退 ----
        problems = assets.validate()
        if problems:
            return {"success": False, "step": "prepare",
                    "error": "；".join(problems)}
        missing_tips = self.config.validate_tips_images()
        if missing_tips:
            return {"success": False, "step": "prepare",
                    "error": f"赞赏图缺失: {missing_tips}"}

        self._report("browser", "正在启动浏览器…", 0.15)
        page = self.session.start(headless=headless)
        try:
            # 步骤1-2：登录（账号密码自动登录，凭据保存在系统凭据库）
            self._report("login", "正在登录（storage_state 缓存有效则直接进，否则自动账号密码登录）…", 0.25)

            def _login_status(message):
                self._report("login", message, 0.25)

            if not self.session.ensure_login(page, on_status=_login_status):
                return {"success": False, "step": "login",
                        "error": self.session.last_login_error or "登录失败（未知原因）"}

            # 步骤3-5：提交作品 → 表情专辑 → 选静态（新建）；
            # 编辑模式：管理页 → 详情 → 「编辑」→ 新标签编辑器（重走全部填表，
            # 预填值被修正值覆盖，最后同样点「提交」）
            if edit:
                self._report("form", "正在打开作品编辑器…", 0.35)
                page = self._step_open_editor(page, assets)
            else:
                self._step_open_submit_form(page)
            # 精准修改模式：need(f) 判定该字段是否要改（非编辑模式恒 True）
            need = (lambda f: True) if not edit or fields is None else (
                lambda f: f in fields)

            if edit:
                if need("stickers"):
                    # 编辑模式：清空旧 16 张 → 重传修好的 → 填含义词
                    self._report("upload", "正在清空旧表情并重新上传…", 0.45)
                    self._step_replace_stickers(page, assets)
                else:
                    self._report("upload", "表情图无需修改，跳过上传", 0.45)
                if edit and need("meanings"):
                    # 步骤7'：含义词与图不符类驳回——只重填词，不动图
                    self._report("meanings", "正在按图重填含义词…", 0.60)
                    self._step_fix_meanings_by_vision(
                        page, sorted({p.stem for p in assets.stickers}))
                if need("album"):
                    # 步骤8-9：专辑名 + 介绍
                    self._report("album", "正在填写专辑信息…", 0.65)
                    self._step_fill_album_info(page, assets)
                # 步骤10：版权（预填，重填无害）
                self._step_fill_copyright(page)
                if need("cover") or need("icon") or need("banner"):
                    # 步骤11-13：横幅/封面/图标（按需只传指定项）
                    self._report("assets", "正在上传横幅/封面/图标…", 0.78)
                    self._step_upload_assets(
                        page, assets,
                        only=[f for f in ("banner", "cover", "icon") if need(f)])
                if need("categories") or need("role"):
                    # 步骤14-18：类型/角色/风格/主题/地区
                    self._report("categories", "正在选择专辑分类…", 0.85)
                    self._step_select_categories(page, assets)
                if need("role"):
                    # 角色分类单独重选（69：合辑→按性别）
                    self._select_role(page, assets)
                if need("price"):
                    # 步骤19：表情价格（免费）
                    self._report("price", "正在选择价格（免费）…", 0.90)
                    self._step_select_price(page)
                if need("tips"):
                    # 步骤20-22：接受赞赏 + 引导语 + 两张赞赏图
                    self._report("tips", "正在配置赞赏图…", 0.94)
                    self._step_tips(page, assets)
            else:
                # ---- 新建模式：素材先传 → 表情图后传（2026-09-02 顺序重构）----
                # 71-89 批量提交全失败事故（同一套代码 61-69 却全过）：16 张
                # 表情图一次 set 后平台异步上传/处理队列被占满，紧随其后的
                # 横幅/封面/图标 set 请求被吞（set 本身不报错，旧的全页计数
                # 判定提前放行），提交时红字「横幅不能为空/封面不能为空」。
                # 老项目 skill 降级经验（经验10 + 实战）：会出问题的素材图
                # 先传、表情图最后传，绕开队列拥堵。新顺序：
                #   赞赏(勾选+引导语+两图) → 横幅/封面/图标(逐个等缩略图)
                #   → 16 张表情图 → 含义词 → 专辑名/介绍/版权 → 分类/价格
                #   → 赞赏兜底（先前未就绪则补） → 提交
                tips_done = False
                if need("tips"):
                    self._report("tips", "正在优先上传赞赏图（避开上传队列拥堵）…", 0.35)
                    try:
                        tips_done = self._step_tips(page, assets)
                    except Exception as e:  # noqa: BLE001
                        self._warn(e)
                if need("cover") or need("icon") or need("banner"):
                    # 步骤11-13 提前：横幅/封面/图标（逐个等各自槽位缩略图）
                    self._report("assets", "正在优先上传横幅/封面/图标…", 0.45)
                    self._step_upload_assets(
                        page, assets,
                        only=[f for f in ("banner", "cover", "icon") if need(f)])
                # 步骤6：上传表情图（按故事线顺序；放在素材之后）
                self._report("upload", f"正在上传 {len(assets.stickers)} 张表情图…", 0.55)
                self._step_upload_stickers(page, assets)
                # 步骤7：填含义词
                self._report("meanings", "正在填写每张表情的含义…", 0.62)
                self._step_fill_meanings(page, assets)
                if need("album"):
                    # 步骤8-9：专辑名 + 介绍
                    self._report("album", "正在填写专辑信息…", 0.70)
                    self._step_fill_album_info(page, assets)
                # 步骤10：版权（预填，重填无害）
                self._step_fill_copyright(page)
                if need("categories") or need("role"):
                    # 步骤14-18：类型/角色/风格/主题/地区
                    self._report("categories", "正在选择专辑分类…", 0.80)
                    self._step_select_categories(page, assets)
                if need("role"):
                    # 角色分类单独重选（69：合辑→按性别；幂等，已选对则跳过）
                    self._select_role(page, assets)
                if need("price"):
                    # 步骤19：表情价格（免费）
                    self._report("price", "正在选择价格（免费）…", 0.86)
                    self._step_select_price(page)
                if need("tips") and not tips_done:
                    # 赞赏区先前未就绪（如勾选/引导语没填上）→ 分类选完后
                    # 区块必然渲染，这里补一轮（幂等：已选跳过、图重传无害）
                    self._report("tips", "赞赏先前未确认成功，正在补传赞赏图…", 0.92)
                    try:
                        self._step_tips(page, assets)
                    except Exception as e:  # noqa: BLE001
                        self._warn(e)
            # 步骤24：提交前自检（实时监测：必填项是否全部就位）
            missing = self._verify_form(page)
            if missing:
                for m in missing:
                    self._warn(f"必填项未填：{m}")
                self._report("verify", f"自检发现 {len(missing)} 项未填，正在重试补填…", 0.96)
                # 自动补填一轮（地区/授权等可能渲染晚）
                self._click_label_all_unchecked(page, "全球")
                self._click_label(page, "免费", check=True)
                self._click_label(page, "接受赞赏", check=True)
                page.wait_for_timeout(1000)
                missing = self._verify_form(page)
                if missing:
                    return {"success": False, "step": "verify",
                            "error": "表单必填项未填全：" + "；".join(missing)
                                     + "。已截图，请到详情页检查素材/名称后重试。",
                            "album_name": assets.album_name,
                            "warnings": list(self.warnings)}
                self._report("verify", "补填完成，必填项已全部就位 ✓", 0.96)

            # 步骤25：提交
            self._report("submit", "正在提交审核…", 0.97)
            ok = self._step_submit(page)
            if not ok:
                try:
                    page.screenshot(path=str(assets.episode_dir / "_publish_error.png"))
                except Exception:  # noqa: BLE001
                    pass
                return {"success": False, "step": "submit",
                        "error": "未检测到提交成功标志（表单可能校验未通过，已截图）",
                        "album_name": assets.album_name,
                        "warnings": list(self.warnings)}
            return {"success": True, "step": "done",
                    "album_name": assets.album_name,
                    "warnings": list(self.warnings)}
        except Exception as e:  # noqa: BLE001 - 保现场
            try:
                page.screenshot(path=str(assets.episode_dir / "_publish_error.png"))
            except Exception as e:  # noqa: BLE001
                self._warn(e)
            return {"success": False, "step": "unknown",
                    "error": f"{type(e).__name__}: {e}",
                    "warnings": list(self.warnings)}
        finally:
            self.session.close()

    # ---- 步骤3-5：开表单 ----

    def _step_open_submit_form(self, page) -> None:
        """步骤3：点"提交作品"；步骤4：选"表情专辑"；步骤5：选静态。"""
        # 步骤3
        page.click(f'button:has-text("{S.SUBMIT_WORK_BUTTON_TEXT}")')
        page.wait_for_load_state("networkidle")
        # 步骤4
        page.click(f'a:has-text("{S.ALBUM_TYPE_TEXT}")')
        page.wait_for_load_state("networkidle")
        # 步骤5：选静态（平台隐藏了 radio input，点可见 label；已选则跳过）
        self._click_label(page, "静态表情", check=True)

    def _step_open_editor(self, page, assets: "EpisodeAssets"):
        """编辑模式入口（2026-08-29 勘察）：管理页 → 目标行「详情」→
        详情页绿色「编辑」→ 新标签打开完整编辑器，返回**新标签 page**
        （调用方用返回值替换工作页；同 context，close 时一并关闭）。

        编辑器与新建表单同构（含义词/专辑名/素材/分类预填），后续步骤照常
        重填修正值，最后 _step_submit 点「提交」重新送审。
        """
        from .status import HOME_URL, normalize_name

        def _goto_list():
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)

        def _click_detail_row() -> bool:
            tn = normalize_name(assets.album_name or assets.episode_dir.name)
            links = page.locator("a:has-text('详情'), td:has-text('详情')")
            for i in range(links.count()):
                el = links.nth(i)
                try:
                    in_tr = el.evaluate("e=>e.closest('tr')!==null")
                    row_txt = (el.locator("xpath=ancestor::tr[1]").inner_text(timeout=2000)
                               if in_tr else el.inner_text(timeout=2000))
                except Exception:
                    continue
                if tn and tn in normalize_name(row_txt):
                    el.click()
                    return True
            return False

        _goto_list()
        # 定位目标行：当前页找不到则翻页继续找（2026-09-01：历史弹导入后
        # 作品 69 个占 8 页）。点击翻页后用页签名验证真的前进了——"下一页"
        # 点击偶发不生效（sync 同款问题），不验证会整轮空转。
        prev_sig = ""
        found = False
        for _ in range(12):
            if _click_detail_row():
                found = True
                break
            nb = page.locator("a:has-text('下一页')")
            if not nb.count():
                break   # 最后一页仍没有 → 真不存在
            nb.first.click(timeout=3000)
            page.wait_for_timeout(2500)
            try:
                cur = "|".join(
                    r.name for r in
                    __import__("sticker_engine.publish.status", fromlist=[
                        "parse_rows_from_text"])
                    .parse_rows_from_text(page.inner_text("body"))[2:5])
            except Exception:   # noqa: BLE001
                cur = ""
            if cur and cur == prev_sig:
                # 没前进：等更久再点一次（SPA 渲染窗口）
                page.wait_for_timeout(2000)
                nb.first.click(timeout=3000)
                page.wait_for_timeout(2500)
            prev_sig = cur
        if not found:
            raise RuntimeError(f"管理页未找到作品行：{assets.album_name}")
        page.wait_for_timeout(6000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(2500)
        # 2026-09-02 平台流程变化（删废品实测发现）：待审核单的详情页
        # 没有「编辑」按钮（此前被当成"审核中锁定"），正确路径是先
        # 「撤回编辑」→确认→状态变「已保存」→再「编辑」。撤回-重提交
        # 正是"修改后重新送审"的平台语义。
        # 2026-09-03 修复（9单重提全卡死根因）：has-text('编辑') 会模糊
        # 匹配「撤回编辑」→ 误判"已有编辑按钮"跳过撤回 → 直接点到的
        # 是「撤回编辑」→ 确认弹框无人处理 → 永远开不了编辑器。
        # 必须 text-is 精确匹配。
        def _strict_edit():
            return page.locator('button:text-is("编辑"), a:text-is("编辑")')

        if not _strict_edit().count():
            withdraw = page.locator(
                "button:has-text('撤回编辑'), a:has-text('撤回编辑')")
            if withdraw.count():
                withdraw.first.click()
                page.wait_for_timeout(1500)
                try:
                    # 2026-09-03 侦察：撤回确认框是 weui-desktop-popover
                    # （非 dialog），旧选择器匹配 0 个 → 确认框永远挂着
                    page.locator(
                        '.weui-desktop-dialog:visible button:has-text("确定"), '
                        '.weui-desktop-popover:visible button:has-text("确定"), '
                        'button:visible:has-text("确定")'
                    ).first.click(timeout=4000)
                except Exception:   # noqa: BLE001
                    pass
                page.wait_for_timeout(3000)
        if not _strict_edit().count():
            raise RuntimeError("详情页既无「编辑」也无「撤回编辑」入口")
        before = set(id(pg) for pg in page.context.pages)
        _strict_edit().first.click()
        page.wait_for_timeout(6000)
        newpage = next((pg for pg in page.context.pages if id(pg) not in before), None)
        if newpage is None:
            raise RuntimeError("点击「编辑」未打开编辑器（无新标签）")
        newpage.wait_for_load_state("domcontentloaded", timeout=30000)
        newpage.wait_for_timeout(3000)
        return newpage

    def _step_delete_cell(self, page, idx: int) -> None:
        """删除编辑器第 idx 格贴纸（1 起，用户按平台格号指令）。"""
        inputs = page.get_by_placeholder("输入含义词")
        inputs.nth(idx - 1).hover(timeout=5000)   # hover 触发头部删除图标
        page.wait_for_timeout(250)
        page.evaluate(
            """(i) => {
              const ins = [...document.querySelectorAll(
                'input[placeholder="输入含义词"]')];
              const inp = ins[i - 1];
              if (!inp) return;
              let cell = inp;
              for (let k = 0; k < 10 && cell; k++) {
                cell = cell.parentElement;
                if (cell && /^[0-9]+/.test((cell.innerText || '').trim())) break;
              }
              const head = cell && cell.querySelector('div[class*="h-7"]');
              if (head) {
                const icons = head.querySelectorAll('img.h-4');
                if (icons.length) icons[0].click();
              }
            }""", idx)
        page.wait_for_timeout(800)

    def _step_set_meaning(self, page, idx: int, word: str) -> None:
        """改编辑器第 idx 格的含义词。"""
        box = page.get_by_placeholder("输入含义词").nth(idx - 1)
        box.fill(word)
        box.dispatch_event("input")
        page.wait_for_timeout(150)

    def _step_fix_meanings_by_vision(self, page, words: list) -> None:
        """编辑器内重填含义词：逐格截图 → codex 从原词集一对一选词 → 填格。

        用于"含义词与图不符"类驳回（58 弹）：图是对的、当年含义词标错位。
        不重传图，只改 16 个含义词文本。
        """
        import tempfile
        from PIL import Image as _Im
        cells = page.locator('div:has(input[placeholder="输入含义词"])')
        n = page.get_by_placeholder("输入含义词").count()
        shots = []
        tmpdir = Path(tempfile.mkdtemp(prefix="meanings_"))
        for i in range(n):
            img = cells.nth(i).locator("img").first
            f = tmpdir / f"cell_{i + 1:02d}.png"
            try:
                img.screenshot(path=str(f), timeout=5000)
                shots.append(f)
            except Exception:   # noqa: BLE001
                shots.append(None)
        # 拼 contact sheet（格序=平台贴纸序）
        valid = [s for s in shots if s]
        if len(valid) < n // 2:
            raise RuntimeError(f"格子截图失败过多（{len(valid)}/{n}）")
        imgs = [_Im.open(str(f)).convert("RGBA") for f in valid if f]
        w = max(im.width for im in imgs)
        h = max(im.height for im in imgs)
        cols = 4
        rows = (len(imgs) + cols - 1) // cols
        sheet = _Im.new("RGB", (w * cols, h * rows), (255, 255, 255, 255))
        for i, im in enumerate(imgs):
            r, c = divmod(i, cols)
            sheet.paste(im, (c * w, r * h), im)
        sheet_path = tmpdir / "_sheet.png"
        sheet.save(sheet_path)
        # codex 一次识图：从词集一对一选词（单行 prompt 铁律）
        prompt = (
            "Image is a contact sheet of sticker cells, numbered 1-" +
            str(len(imgs)) + " from left to right, top to bottom. For EACH "
            "cell pick the ONE best-matching meaning word from this fixed "
            "candidate list: " + "、".join(words) + ". Each word must be used "
            "EXACTLY once. Answer ONLY with JSON like {\"1\":\"词\"} using "
            "all " + str(len(imgs)) + " words.")
        text = self.vision.codex.exec_text(prompt=prompt,
                                           refs=[sheet_path], timeout=300)             if hasattr(self, "vision") else ""
        if not text:
            from ..providers.codex import CodexProvider
            text = CodexProvider(codex_exec=self.config.codex_exec,
                                 output_dir=self.config.codex_output_dir)                 .exec_text(prompt=prompt, refs=[sheet_path], timeout=300)                 if hasattr(self.config, "codex_exec") else ""
        if not text or "{" not in text:
            raise RuntimeError("含义词识图失败（codex 无有效输出）")
        import json as _json
        m = _json.loads(text[text.index("{"): text.rindex("}") + 1])
        # 填格（格序=截图序）。用 evaluate 直设 value——个别格子 input
        # 处于不可见态（Vue 条件渲染），fill 的 actionability 检查会卡死
        for i in range(n):
            word = m.get(str(i + 1), "")
            if not word:
                continue
            self._set_meaning_value(page, i + 1, word)
        # 平台硬规则（56/58 驳回）：含义词不得重复。codex 可能不守
        # "每个词恰好一次"的约定 → 读回全部格子查重，对重复格（保留
        # 首个）用语气词/标点变体重填——不用 XX1/XX2 数字后缀（平台
        # 明文拒绝该形式）。
        values = self._read_meanings(page, n)
        dup_cells = []
        seen = set()
        for i, v in enumerate(values, start=1):
            v = (v or "").strip()
            if v and v in seen:
                dup_cells.append(i)
            seen.add(v)
        if dup_cells:
            self._warn(f"含义词识图重填后仍有重复（第 {dup_cells} 格），换变体词")
            used = [v.strip() for v in values if (v or "").strip()]
            for i in dup_cells:
                base_word = (values[i - 1] or "").strip()
                variant = self._meaning_variant(base_word, used)
                self._set_meaning_value(page, i, variant)
                used.append(variant)
            final = self._read_meanings(page, n)
            filled = [v.strip() for v in final if (v or "").strip()]
            if len(filled) != len(set(filled)):
                self._warn("含义词变体替换后仍存在重复，需人工检查")

    @staticmethod
    def _meaning_variant(word: str, used: list) -> str:
        """给重复词生成不重复的变体（中文语气词优先，非数字后缀——
        平台可能过滤标点/特殊符号，汉字后缀最稳）。"""
        for suffix in ("呀", "呢", "哦", "啦", "哟", "嘛", "哈"):
            cand = f"{word}{suffix}"
            if cand not in used and len(cand) <= 8:
                return cand
        for k in range(2, 50):
            cand = f"{word}{'呐' * k}"[:8]
            if cand not in used:
                return cand
        return f"{word}x"

    def _read_meanings(self, page, n: int) -> list:
        """读回编辑器全部含义词输入框的当前值。"""
        try:
            vals = page.evaluate(
                """(sel) => [...document.querySelectorAll(sel)]
                       .map(i => i.value || '')""",
                'input[placeholder="输入含义词"]')
            return list(vals) if isinstance(vals, list) else []
        except Exception:   # noqa: BLE001
            return []

    def _set_meaning_value(self, page, idx: int, word: str) -> None:
        """直设第 idx 格含义词并**读回验证**（56/58 重提实测：平台表单是
        React 受控组件，`inp.value=w` 会被下次渲染重置回旧值——必须用
        nativeInputValueSetter 绕过 valueTracker；仍不行再 fill 真实键入）。"""
        js = """([i, w]) => {
          const ins = [...document.querySelectorAll(
            'input[placeholder="输入含义词"]')];
          const inp = ins[i - 1];
          if (!inp) return 'noInput';
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(inp, w);
          inp.dispatchEvent(new Event('input', {bubbles: true}));
          inp.dispatchEvent(new Event('change', {bubbles: true}));
          return inp.value;
        }"""
        for attempt in range(2):
            try:
                got = str(page.evaluate(js, [idx, word]) or "")
            except Exception:   # noqa: BLE001
                got = ""
            if got == word:
                return
            # native setter 也未生效 → fill 走真实输入路径（focus+键盘）
            try:
                box = page.get_by_placeholder("输入含义词").nth(idx - 1)
                box.fill(word, timeout=4000)
                page.wait_for_timeout(150)
            except Exception:   # noqa: BLE001
                pass
            try:
                got = str(page.evaluate(
                    """(i) => {
                      const ins = [...document.querySelectorAll(
                        'input[placeholder="输入含义词"]')];
                      return ins[i - 1] ? ins[i - 1].value : '';
                    }""", idx) or "")
            except Exception:   # noqa: BLE001
                got = ""
            if got == word:
                return

    def _step_replace_stickers(self, page, assets: EpisodeAssets) -> None:
        """编辑模式：清空已有贴纸 → 重传修好的 16 张 → 填含义词。

        2026-09-01 实测（62 单）：编辑器已上传的表情图无单张替换/删除入口
        之外，整体重传=追加；但**每个编号格 hover 后头部第一个图标是删除**
        （无确认弹窗，直接删）——先删光再传，实现"替换"语义。
        """
        # 1) 删光旧贴纸：真实 hover 第一格触发删除图标 → 点头部第一个图标
        # （无确认弹窗；上限 32 防失控；删一张停一下等布局稳定）
        for _ in range(32):
            inputs = page.get_by_placeholder("输入含义词")
            n = inputs.count()
            if n == 0:
                break
            inputs.nth(0).hover(timeout=5000)   # hover 触发删除图标出现
            page.wait_for_timeout(250)
            page.evaluate(
                """() => {
                  const inp = document.querySelector(
                    'input[placeholder="输入含义词"]');
                  if (!inp) return;
                  let cell = inp;
                  for (let k = 0; k < 10 && cell; k++) {
                    cell = cell.parentElement;
                    if (cell && /^[0-9]+/.test((cell.innerText || '').trim())) break;
                  }
                  const head = cell && cell.querySelector('div[class*="h-7"]');
                  if (head) {
                    const icons = head.querySelectorAll('img.h-4');
                    if (icons.length) icons[0].click();
                  }
                }""")
            page.wait_for_timeout(800)
            if page.get_by_placeholder("输入含义词").count() >= n:
                break   # 这一格删不动（无删除入口），防死循环
        left = page.get_by_placeholder("输入含义词").count()
        if left:
            raise RuntimeError(f"旧贴纸未清空（剩 {left} 张），中止重传防追加")
        # 2) 重传修好的 16 张 + 填含义词
        self._step_upload_stickers(page, assets)
        self._step_fill_meanings(page, assets)

    # ---- 步骤6：上传表情图 ----

    def _step_upload_stickers(self, page, assets: EpisodeAssets) -> None:
        """步骤6：上传表情图（按故事线顺序，set_input_files 多文件）。"""
        # 多文件 input（accept 含 image/* 或无限制的 file input）
        # A 产出 16 张 .png，用一个 input[type=file] 一次提交
        paths = [str(s) for s in assets.stickers]
        # 经验：表情图 file input 是第一个 input[type=file]
        # （图标 input 是第 4 个 accept=image/png，横幅/封面/赞赏在后面）
        file_inputs = page.query_selector_all('input[type="file"]')
        target = None
        for fi in file_inputs:
            accept = fi.get_attribute("accept") or ""
            # 表情图 input 通常 accept 含 .png 且允许多选，排除图标专用
            if ".png" in accept or accept == "":
                target = fi
                break
        if target is not None:
            target.set_input_files(paths)
        else:
            # 回退：直接 set_input_files 第一个
            page.set_input_files('input[type="file"]', paths)
        # 等待上传（按数量动态等）
        page.wait_for_timeout(max(10000, len(paths) * 2000))

    # ---- 步骤7：填含义词 ----

    def _step_fill_meanings(self, page, assets: EpisodeAssets) -> None:
        """步骤7：填含义词（evaluate 设 value + dispatch input 事件，比 type 快）。

        2026-09-02 加固（71 单实测）：表情图上传后含义词输入框是**逐个
        渲染**的（裁剪框挂着时更是只渲染出第 1 格）——填完必须验证
        「格数够 + 每格有值」，不足等 1s 重填，最多 3 轮。
        把选择器作为参数传给 JS（避免字符串拼接转义出错）。
        """
        for attempt in range(3):
            page.evaluate(
                """([meanings, selector]) => {
                    const inputs = document.querySelectorAll(selector);
                    for (let i = 0; i < inputs.length && i < meanings.length; i++) {
                        inputs[i].value = meanings[i];
                        inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                        inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
                [assets.meanings, S.MEANING_INPUT],
            )
            page.wait_for_timeout(1000)
            try:
                state = page.evaluate(
                    """(sel) => {
                        const ins = [...document.querySelectorAll(sel)];
                        return {n: ins.length,
                                filled: ins.filter(i => (i.value || '').trim()).length};
                    }""", S.MEANING_INPUT)
            except Exception:   # noqa: BLE001
                state = None
            n = state.get("n", 0) if isinstance(state, dict) else 0
            filled = state.get("filled", 0) if isinstance(state, dict) else 0
            if n >= len(assets.meanings) and filled >= len(assets.meanings):
                return
            self._warn(f"含义词第 {attempt + 1} 次填写后 "
                       f"{filled}/{len(assets.meanings)} 格有值"
                       f"（渲染出 {n} 格），重填")

    # ---- 步骤8-9：专辑名 + 介绍 ----

    def _step_fill_album_info(self, page, assets: EpisodeAssets) -> None:
        """步骤8：专辑名；步骤9：介绍（选后验证+兜底，59/60 事故收尾）。"""
        page.fill(S.ALBUM_NAME_INPUT, assets.album_name)
        if assets.intro:
            for attempt in range(2):
                try:
                    page.fill(S.INTRO_TEXTAREA, assets.intro, timeout=5000)
                    page.wait_for_timeout(500)
                    val = page.locator(S.INTRO_TEXTAREA).input_value(timeout=3000)
                    if val and val.strip():
                        return
                    self._warn(f"介绍第 {attempt + 1} 次填写后为空，重填")
                except Exception as e:  # noqa: BLE001
                    self._warn(f"介绍填写异常（第 {attempt + 1} 次）：{e}")
                    try:   # 兜底：placeholder 变了就找任意 textarea
                        page.locator("textarea").first.fill(assets.intro)
                        page.wait_for_timeout(500)
                        return
                    except Exception:   # noqa: BLE001
                        pass

    # ---- 步骤10：版权 ----

    def _step_fill_copyright(self, page) -> None:
        """步骤10：版权信息（固定值，config 可改）。"""
        try:
            page.fill(S.COPYRIGHT_INPUT, self.config.copyright)
        except Exception as e:  # noqa: BLE001
            self._warn(e)

    # ---- 步骤11-13：横幅/封面/图标 ----

    # only 参数的英文键 → 中文标签映射（71-89 全军覆没的根因：主流程传
    # 英文键 ["banner","cover","icon"]，这里却用中文标签做 in 匹配 →
    # pairs 被过滤成空 → 素材上传整体空转、零告警 → 提交红字"横幅不能为空"）
    _ASSET_ONLY_ALIAS = {"banner": "横幅", "cover": "封面", "icon": "图标"}

    def _step_upload_assets(self, page, assets: EpisodeAssets, only=None) -> None:
        """步骤11-13：横幅、封面、图标。only=[键,...] 时只传指定项（精准修改）。

        only 同时接受中文标签（"横幅"）和英文键（"banner"）——2026-09-02
        破案：两套键名不一致曾让上传整体空转（见 _ASSET_ONLY_ALIAS 注释）。
        2026-08 实测：页面改版后 uploader__init 消失；表单上的可见 file
        input 槽位顺序即 横幅/封面/图标（横幅 accept 含 jpeg，封面/图标
        accept=image/png）。
        2026-09-02 重构（71-89 批量失败事故）：
        ①每张素材上传后等**自己槽位**出现新缩略图（旧的全页计数判定会
          提前放行），超时自动重传一次；
        ②图标定位从「最后一个 png」改为「封面之后第一个 png」——赞赏图
          提前上传后其 input 已渲染（accept 同为 png），旧定位会把图标
          错传进赞赏致谢图槽。
        """
        if only:
            only = {self._ASSET_ONLY_ALIAS.get(f, f) for f in only}
        pairs = [("横幅", assets.banner), ("封面", assets.cover), ("图标", assets.icon)]
        if only:
            pairs = [(l, i) for l, i in pairs if l in only]
        for label, img in pairs:
            if img is None:
                self._warn(f"{label}文件缺失，跳过上传（详情页可重新生成）")
                continue
            ok = False
            for attempt in range(2):   # 未见缩略图 → 重传一次（防异步吞请求）
                if attempt > 0:
                    # 先清掉可能挂着的裁剪框（上一轮漏点确定会让重传也无效）
                    self._confirm_crop(page, wait_seconds=2.0)
                try:
                    if self._upload_asset(page, label, img):
                        ok = True
                        break
                except Exception as e:  # noqa: BLE001
                    self._warn(f"{label}第 {attempt + 1} 次上传异常：{e}")
                    continue
                self._warn(f"{label}第 {attempt + 1} 次上传后未见缩略图，重试")
            if not ok:
                self._warn(f"{label}两次上传后均未确认缩略图，提交可能被平台拒绝")

    def _upload_asset(self, page, label: str, img: Path) -> bool:
        """上传单张素材并等它的槽位出现新缩略图。返回是否确认成功。"""
        info = page.evaluate("""(label) => {
          // 可见性过滤：表情图 drop zone（页面顶部隐藏 input，accept 同样
          // 含 jpeg）会抢走横幅槽位（59/60 两单事故），必须排除
          const vis = el => !!(el.offsetParent || el.getClientRects().length);
          const files = [...document.querySelectorAll('input[type=file]')]
            .filter(vis);
          const hasJpg = f => ['jpeg', 'jpg'].some(w => (f.accept || '').includes(w));
          const hasPng = f => (f.accept || '').includes('png');
          // 槽位：横幅=第一个含 jpeg 的；封面=其后第一个 png；
          // 图标=封面之后第一个 png（不用「最后一个 png」：赞赏图先传后
          // 其 input（accept 也含 png）已渲染，会抢走图标槽位）
          const b = files.findIndex(hasJpg);
          let c = -1, idx = -1;
          if (label === '横幅') {
            idx = b;
          } else {
            if (c < 0) c = files.findIndex((f, i) => i > b && hasPng(f));
            if (label === '封面') idx = c;
            else idx = files.findIndex((f, i) => i > c && hasPng(f));
          }
          if (idx < 0) return {ok: false, srcs: []};
          files.forEach(f => f.classList.remove('_asset_target'));
          files[idx].classList.add('_asset_target');
          // zone：从 input 向上找最近的「上传卡」容器（内含格式说明文字、
          // 宽度有限、file input 数 ≤ 1），打 _asset_zone 标记
          document.querySelectorAll('._asset_zone')
            .forEach(z => z.classList.remove('_asset_zone'));
          let zone = files[idx];
          for (let k = 0; k < 12 && zone; k++) {
            zone = zone.parentElement;
            if (!zone) break;
            const ownFiles = zone.querySelectorAll('input[type=file]').length;
            const txt = zone.innerText || '';
            const w = zone.getBoundingClientRect().width;
            if (ownFiles <= 1 && w > 40 && w < 800
                && (txt.includes('JPG') || txt.includes('PNG')
                    || txt.includes('jpg') || txt.includes('png')
                    || txt.includes('格式'))) {
              break;
            }
          }
          const srcs = zone
            ? [...zone.querySelectorAll('img')]
                .map(i => i.src || i.getAttribute('src') || '')
            : [];
          if (zone) zone.classList.add('_asset_zone');
          return {ok: true, zone: !!zone, srcs};
        }""", label)
        # mock/异常容错：info 可能不是 dict（测试里 evaluate 返回 True）
        if not info:
            self._warn(f"{label}：页面上找不到对应上传控件（可能改版）")
            return False
        prev_srcs = info.get("srcs", []) if isinstance(info, dict) else []
        has_zone = info.get("zone", False) if isinstance(info, dict) else True
        try:
            page.set_input_files('._asset_target', str(img))
        except Exception as e:  # noqa: BLE001
            self._warn(f"{label} set_input_files 失败：{e}")
            return False
        page.wait_for_timeout(1500)
        self._confirm_crop(page)
        if not has_zone:
            # zone 没找到：退化用旧的全页计数判定（聊胜于无）
            need_kw = "JPG 或 PNG" if label == "横幅" else "PNG 格式"
            page.wait_for_function(
                """([kw, nth]) => {
                  const zones = [...document.querySelectorAll('div')]
                    .filter(d => d.querySelectorAll('img').length
                             && (d.innerText || '').includes(kw)
                             && d.getBoundingClientRect().width > 50
                             && d.getBoundingClientRect().width < 400);
                  return zones.length >= nth;
                }""",
                arg=[need_kw, 1 if label != "图标" else 2],
                timeout=20000)
            page.wait_for_timeout(500)
            return True
        # 槽位级确认：zone 内出现**新增的可见 img，且不在裁剪 dialog 子树内**
        # （2026-09-02 破案：裁剪框挂在 zone 里，其预览图曾被误判为上传
        # 成功的缩略图 → 假阳性 → 未点「确定」→ 提交红字「横幅不能为空」）
        page.wait_for_function(
            """(prevSrcs) => {
              const z = document.querySelector('._asset_zone');
              if (!z) return false;
              return [...z.querySelectorAll('img')].some(im => {
                if (im.closest('.weui-desktop-dialog__wrp')) return false;
                const s = im.src || im.getAttribute('src') || '';
                if (!s || prevSrcs.includes(s)) return false;
                return !!(im.offsetParent || im.getClientRects().length);
              });
            }""",
            arg=prev_srcs, timeout=25000)
        page.wait_for_timeout(500)
        return True

    def _upload_uploader_at(self, page, index: int, img_path: Path) -> None:
        """上传到第 index 个 uploader__init 区域，处理裁剪框确定。"""
        # UPLOADER_INIT 指向 div.uploader__init span.weui-desktop-icon__add
        uploaders = page.query_selector_all(S.UPLOADER_INIT)
        if index >= len(uploaders):
            return
        # 给对应 uploader 内的 file input 打标记，再 set_input_files
        page.evaluate(
            """(idx) => {
                const ups = document.querySelectorAll('div.uploader__init');
                const up = ups[idx];
                const input = up ? up.querySelector('input[type="file"]') : null;
                if (input) input.className = '_target_input_' + idx;
                return !!(input);
            }""",
            index,
        )
        target_cls = f"._target_input_{index}"
        try:
            page.set_input_files(target_cls, str(img_path))
        except Exception as e:  # noqa: BLE001
            self._warn(e)
        # 经验13：uploadFile 后若有裁剪框，点确定
        self._confirm_crop(page)
        page.wait_for_timeout(2000)

    # ---- 平台控件通用操作（2026-08 页面实测） ----
    # 平台把 radio/checkbox 的 input 全部隐藏（label 样式化），
    # 直接点 input 必超时——统一改为点可见 label 文本。

    def _click_label(self, page, text: str, check: bool = False) -> bool:
        """点含指定文本的可见 label。check=True 时已选中则跳过（防 toggle 取消）。"""
        try:
            done = page.evaluate("""(args) => {
              const [text, check] = args;
              const vis = el => !!(el.offsetParent || el.getClientRects().length);
              const labels = [...document.querySelectorAll('label')]
                .filter(l => (l.innerText || '').trim() === text && vis(l));
              if (check) {
                for (const lb of labels) {
                  const input = lb.querySelector('input');
                  if (input && input.checked) return true;
                }
              }
              for (const lb of labels) {
                lb.click();
                return true;
              }
              return false;
            }""", [text, check])
            if not done:
                self._warn(f"找不到可点的选项「{text}」")
                return False
            return True
        except Exception as e:  # noqa: BLE001
            self._warn(e)
            return False

    def _click_label_all_unchecked(self, page, text: str) -> None:
        """把页面上所有含指定文本且未选中的 label 组都点一遍（用于上架+下载两组地区）。"""
        try:
            page.evaluate("""(text) => {
              const vis = el => !!(el.offsetParent || el.getClientRects().length);
              for (const lb of document.querySelectorAll('label')) {
                if ((lb.innerText || '').trim() !== text || !vis(lb)) continue;
                const input = lb.querySelector('input');
                if (!input || !input.checked) lb.click();
              }
            }""", text)
        except Exception as e:  # noqa: BLE001
            self._warn(e)

    def _verify_form(self, page) -> list:
        """提交前自检必填项（实时监测：哪些还没填上）。返回缺失列表。"""
        try:
            missing = page.evaluate("""() => {
              const vis = el => !!(el.offsetParent || el.getClientRects().length);
              const missing = [];
              const labelChecked = (text) => {
                for (const lb of document.querySelectorAll('label')) {
                  if ((lb.innerText || '').trim() === text && vis(lb)) {
                    const input = lb.querySelector('input');
                    if (input && input.checked) return true;
                  }
                }
                return false;
              };
              if (!labelChecked('静态表情')) missing.push('类型·静态表情');
              if (!labelChecked('卡通表情/其他')) missing.push('类型·卡通表情/其他');
              if (!labelChecked('软萌可爱') && !labelChecked('日常')) missing.push('表情风格');
              if (!labelChecked('万能通用')) missing.push('表情主题');
              const globals = [...document.querySelectorAll('label')]
                .filter(l => (l.innerText || '').trim() === '全球' && vis(l));
              const checkedGlobals = globals
                .filter(l => { const i = l.querySelector('input'); return i && i.checked; }).length;
              if (globals.length && checkedGlobals < globals.length)
                missing.push('上架/下载地区 仅选了 ' + checkedGlobals + '/' + globals.length + ' 组');
              if (!labelChecked('免费')) missing.push('表情价格');
              if (!labelChecked('接受赞赏')) missing.push('表情赞赏');
              const nameInput = document.querySelector('input[placeholder*="表情专辑名称"]');
              if (nameInput && !nameInput.value.trim()) missing.push('名称');
              const intro = document.querySelector('textarea[placeholder*="特点和故事"]');
              if (intro && !intro.value.trim()) missing.push('介绍');
              const cp = document.querySelector('input[placeholder*="版权信息"]');
              if (cp && !cp.value.trim()) missing.push('版权');
              const dt = document.querySelector('.weui-desktop-form__dropdowncascade__dt');
              if (dt) {
                const t = (dt.innerText || '').trim();
                // dt 选完形如"人物角色女人"（逗号是 CSS 分隔样式不进文本）
                const lv2 = t.includes('女人') || t.includes('男人')
                  || t.includes('人物合辑') || t.includes('人物角色-');
                if (t.includes('未选择') || !lv2)
                  missing.push('角色/内容(级联未到二级)');
              }
              return missing;
            }""")
            return list(missing) if isinstance(missing, list) else []
        except Exception:
            return []

    def _confirm_crop(self, page, wait_seconds: float = 8.0) -> None:
        """上传素材后可能弹出「裁剪横幅/封面/图标」dialog（图片需手动
        确认尺寸才生效——2026-09-02 真机破案：71-89 事故里横幅/封面/
        图标 set 后平台弹裁剪框，不点「确定」上传就不落地，提交时红字
        「横幅不能为空」，且挂着的裁剪预览图会被误判成上传成功缩略图）。

        轮询最多 wait_seconds 等**可见** dialog 出现；出现则点其中的
        「确定」；无 dialog（赞赏组件/直传成功路径）快速退出。
        """
        # 迭代上限而非纯时间 deadline（避免无框时忙等；间隔靠
        # wait_for_timeout，真实环境 14×600ms ≈ 8.4s 封顶）
        n_iters = max(1, int(wait_seconds / 0.6))
        for _ in range(n_iters):
            state = page.evaluate("""() => {
              const vis = el => !!(el.offsetParent || el.getClientRects().length);
              const wrps = [...document.querySelectorAll(
                '.weui-desktop-dialog__wrp')].filter(w => vis(w));
              if (!wrps.length) return 'none';
              for (const w of wrps) {
                const btns = [...w.querySelectorAll('button, a')].filter(vis);
                const ok = btns.find(b =>
                  ((b.innerText || '').replace(/\\s+/g, '')) === '确定');
                if (ok) { ok.click(); return 'clicked'; }
              }
              return 'noBtn';
            }""")
            if state == "clicked":
                page.wait_for_timeout(800)   # 等 dialog 收起 + 上传落地
                return
            if state == "noBtn":
                return   # 有框但找不到确定按钮：异常，不死等
            page.wait_for_timeout(600)

    # ---- 步骤14-18：类型/角色/风格/主题/地区 ----

    def _step_select_categories(self, page, assets: EpisodeAssets) -> None:
        """步骤14-19：类型/角色/风格/主题/上架+下载地区/授权。

        2026-08 实测：平台的 radio/checkbox input 全部隐藏，必须点 label 文本；
        上架地区和下载地区是两组独立的"全球/中国大陆"，两组都要选。
        """
        # 步骤14：类型细分（卡通表情/其他）
        self._click_label(page, "卡通表情/其他", check=True)
        # 步骤15：角色/内容级联下拉（含捞鱼→人物合辑，不含→女人）
        self._select_role(page, assets)
        # 步骤16：风格（软萌可爱 + 日常，都勾）
        self._click_label(page, "软萌可爱", check=True)
        self._click_label(page, "日常", check=True)
        # 步骤17：主题（万能通用）
        self._click_label(page, "万能通用", check=True)
        # 步骤18-19：上架地区 + 下载地区（两组都选全球；已选的跳过）
        self._click_label_all_unchecked(page, "全球")
        # 注意：「涉及肖像权/版权授权」不能勾——那是声明使用了他人肖像/版权，
        # 勾上会要求上传「证明文件」（自创角色无需授权，保持未勾选状态）

    def _select_role(self, page, assets: EpisodeAssets) -> None:
        """步骤15：角色/内容级联下拉（点开→一级→二级，选后验证+重试）。

        2026-09-02 修复（59/60 事故）：①点击必须落在**文本叶子**上（事件绑
        在叶子，点 title 容器不触发）；②选后验证 dt 文本含目标二级值，失败
        重试 3 次——旧版静默失败时 dt 停在一级"人物角色"，本地 verify 检
        "未选择"能过、平台却报"角色/内容不能为空"。
        """
        chars = getattr(assets, "characters", []) or []
        if len(chars) >= 2:
            target = S.ROLE_WITH_LAOYU_TITLE.split("(")[0]
        elif chars and chars[0] in S.ROLE_MALE_NAMES:
            target = S.ROLE_MALE_TITLE
        else:
            target = S.ROLE_WITHOUT_LAOYU_TITLE.split("(")[0]

        for attempt in range(3):
            try:
                page.click(S.ROLE_DROPDOWN_DT, timeout=4000)
                page.wait_for_selector(
                    ".weui-desktop-dropdown__list-ele.first-level",
                    timeout=5000, state="attached")
                page.click(
                    f'.weui-desktop-dropdown__list-ele.first-level:has-text("'
                    f'{S.ROLE_FIRST_LEVEL}")', timeout=4000)
                page.wait_for_selector(f'[title*="{target}"]', timeout=6000,
                                       state="attached")
                try:
                    page.get_by_text(target, exact=True).first.click(timeout=3000)
                except Exception:   # noqa: BLE001
                    page.click(f'[title*="{target}"]', timeout=3000)
                page.wait_for_timeout(1000)
                dt_text = page.locator(S.ROLE_DROPDOWN_DT).inner_text(timeout=3000)
                if target in dt_text:
                    return
                self._warn(f"角色/内容第 {attempt + 1} 次选择后 dt="
                           f"{dt_text.strip()[:20]}，重试")
            except Exception as e:   # noqa: BLE001
                self._warn(f"角色/内容选择异常（第 {attempt + 1} 次）：{e}")
        self._warn(f"角色/内容最终未确认选中【{target}】，提交可能被平台拒绝")

    # ---- 步骤19：表情价格（免费） ----

    def _step_select_price(self, page) -> None:
        """步骤20：表情价格（免费）——点可见 label，已选跳过。"""
        self._click_label(page, "免费", check=True)

    # ---- 步骤20-22：赞赏 ----

    def _step_tips(self, page, assets: EpisodeAssets) -> bool:
        """步骤20：接受赞赏；步骤21：赞赏引导语；步骤22-23：上传两张赞赏图。

        返回是否全部确认成功（勾选+引导语+两图缩略图）——新建模式下赞赏
        提前到素材阶段，若区块未渲染会返回 False，主流程在分类选完后兜底
        重跑一轮（幂等）。
        """
        # 步骤21：接受赞赏（平台隐藏 checkbox，点 label；已选跳过防取消）
        ok_accept = self._click_label(page, "接受赞赏", check=True)
        # 步骤21：赞赏引导语
        ok_text = True
        try:
            page.fill(S.TIPS_TEXT_INPUT, self.config.thanks_text, timeout=3000)
        except Exception as e:  # noqa: BLE001
            ok_text = False
            self._warn(e)
        # 步骤22-23：上传赞赏引导图 + 致谢图
        ok_imgs = self._upload_tip_images(page, assets)
        return bool(ok_accept and ok_text and ok_imgs)

    def _upload_tip_images(self, page, assets: EpisodeAssets) -> bool:
        """上传赞赏引导图 + 致谢图。返回两张是否都确认出现缩略图。

        定位策略（迁移原 skill 方案 A）：逐个 file input 向上找祖先文字，匹配
        "赞赏引导图/引导图" 或 "赞赏致谢图/致谢图"。失败回退：按 uploader__init
        最后两个。上传后处理裁剪框确定（经验13）+ 槽位级缩略图确认（经验12）。
        """
        pairs = [
            (["赞赏引导图", "引导图"],
             getattr(assets, "tip_guide", None) or self.config.tip_guide_img),
            (["赞赏致谢图", "致谢图"],
             getattr(assets, "tip_thanks", None) or self.config.tip_thanks_img),
        ]
        all_ok = True
        for keywords, img_path in pairs:
            ok = False
            try:
                ok = self._upload_tip_by_label(page, keywords, Path(img_path))
            except Exception:  # noqa: BLE001
                # 回退：最后两个 uploader__init
                try:
                    self._upload_uploader_last(page, keywords, Path(img_path))
                    ok = True   # 回退路径无槽位级确认，仅尽力而为
                except Exception as e:  # noqa: BLE001
                    self._warn(f"{'/'.join(keywords)} 上传失败：{e}")
            if not ok:
                all_ok = False
        return all_ok

    def _upload_tip_by_label(self, page, keywords, img_path: Path) -> bool:
        """按文字标签定位 file input 并上传，等槽位缩略图出现（经验12）。"""
        info = page.evaluate(
            """(kws) => {
                const inputs = document.querySelectorAll('input[type="file"]');
                for (let i = 0; i < inputs.length; i++) {
                    let p = inputs[i];
                    for (let k = 0; k < 8 && p; k++) {
                        const t = (p.innerText || p.textContent || '').trim();
                        if (t && t.length < 120 && kws.some(w => t.includes(w))) {
                            // 给命中的 input 打标 + 向上找含标签文字的容器
                            inputs.forEach(x => x.classList.remove('_tip_target'));
                            inputs[i].classList.add('_tip_target');
                            let zone = inputs[i];
                            for (let z = 0; z < 10 && zone; z++) {
                                zone = zone.parentElement;
                                if (!zone) break;
                                const txt = zone.innerText || '';
                                if (kws.some(w => txt.includes(w))
                                    && zone.getBoundingClientRect().width < 900
                                    && zone.querySelectorAll('input[type=file]').length <= 1) {
                                    break;
                                }
                            }
                            document.querySelectorAll('._tip_zone')
                              .forEach(x => x.classList.remove('_tip_zone'));
                            const srcs = zone ? [...zone.querySelectorAll('img')]
                                .map(im => im.src || im.getAttribute('src') || '') : [];
                            if (zone) zone.classList.add('_tip_zone');
                            return {idx: i, srcs};
                        }
                        p = p.parentElement;
                    }
                }
                return {idx: -1, srcs: []};
            }""",
            keywords,
        )
        idx = info.get("idx", -1) if isinstance(info, dict) else (
            info if isinstance(info, int) else -1)
        if idx < 0:
            raise RuntimeError(f"未找到含 {keywords} 的 file input")
        file_inputs = page.query_selector_all('input[type="file"]')
        if idx >= len(file_inputs):
            raise RuntimeError(f"file input 索引 {idx} 越界")
        prev_srcs = info.get("srcs", []) if isinstance(info, dict) else []
        file_inputs[idx].set_input_files(str(img_path))
        page.wait_for_timeout(1500)
        self._confirm_crop(page)
        # 槽位级缩略图确认（同 _upload_asset：等 zone 内出现新增 img，
        # 排除裁剪 dialog 子树内的预览图，防假阳性）
        try:
            page.wait_for_function(
                """(prevSrcs) => {
                  const z = document.querySelector('._tip_zone');
                  if (!z) return false;
                  return [...z.querySelectorAll('img')].some(im => {
                    if (im.closest('.weui-desktop-dialog__wrp')) return false;
                    const s = im.src || im.getAttribute('src') || '';
                    if (!s || prevSrcs.includes(s)) return false;
                    return !!(im.offsetParent || im.getClientRects().length);
                  });
                }""",
                arg=prev_srcs, timeout=20000)
        except Exception as e:  # noqa: BLE001
            self._warn(f"{'/'.join(keywords)} 上传后未见缩略图：{e}")
            return False
        page.wait_for_timeout(500)
        return True

    def _upload_uploader_last(self, page, keywords, img_path: Path) -> None:
        """赞赏图回退：用 uploader__init 倒数第 1/2 个。"""
        # 记录已用回退槽位数（实例属性懒初始化）
        n_used = getattr(self, "_tip_fallback_used", 0)
        uploaders = page.query_selector_all(S.UPLOADER_INIT)
        if len(uploaders) < 2:
            return
        # 倒数第 2（引导图）= -2 + n_used；致谢图 = -1 + n_used
        idx_from_end = -2 + n_used
        uploader_index = len(uploaders) + idx_from_end
        if uploader_index < 0:
            return
        self._upload_uploader_at(page, uploader_index, img_path)
        self._tip_fallback_used = n_used + 1

    # ---- 步骤23：提交 ----

    def _step_submit(self, page) -> bool:
        """步骤23：点提交，严格等待成功标志。

        判定收紧（修复"假提交成功"——原来 URL 不含 login/readtemplate 就算过）：
        1. 明确成功：页面出现"提交成功"，或 URL 回到管理首页（home/index）；
        2. 明确失败：仍停在表单页且出现校验错误提示（必填/请填写等）；
        3. 轮询 60 秒仍无明确标志 → 判失败（调用方截图保现场）。
        """
        # 2026-09-02 修复：必须精确匹配「提交」（text-is）——顶部「提交作品」
        # 按钮同是 btn_primary，:has-text 模糊匹配会点到它 → 打开全新空白
        # 表单 → 空表单的"请填写"提示被误判为校验失败（61-69 之后平台把
        # 顶部按钮也改成了 primary 样式，59/60 事故连环根因之一）
        page.click(
            f'button.weui-desktop-btn_primary:text-is("{S.SUBMIT_BUTTON_TEXT}")',
            timeout=8000,
        )
        for _ in range(12):   # 最多 60 秒
            page.wait_for_timeout(5000)
            try:
                body = page.inner_text("body", timeout=5000)
            except Exception:  # noqa: BLE001
                body = ""
            if "提交成功" in body:
                return True
            url = page.url
            # 回到管理首页 = 提交后跳转成功
            if "home/index" in url and "login" not in url:
                return True
            # 停在表单页：检测平台校验错误 → 明确失败并收集具体红字字段
            for err_kw in ("请填写", "必填", "不能为空", "提交失败", "格式不正确", "请完善"):
                if err_kw in body:
                    try:
                        reds = page.evaluate(
                            """() => {
                              const out = [];
                              for (const el of document.querySelectorAll('*')) {
                                const t = el.textContent.trim();
                                if (t.includes('不能为空') && el.children.length === 0
                                    && el.getBoundingClientRect().width > 0) {
                                  let p = el.parentElement, ctx = '';
                                  for (let k = 0; k < 4 && p; k++) {
                                    p = p.parentElement;
                                    if (p) { ctx = (p.innerText || '').trim().split('\n')[0].slice(0, 20); if (ctx) break; }
                                  }
                                  out.push(ctx + '→' + t.slice(0, 20));
                                }
                                if (out.length >= 6) break;
                              }
                              return out;
                            }""")
                    except Exception:   # noqa: BLE001
                        reds = []
                    self._warn(f"平台校验未通过：页面提示含「{err_kw}」"
                               + (f"，具体：{reds}" if reds else ""))
                    return False
        return False
