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

        # ---- 角色卡：是否含捞鱼 ----
        contains_laoyu = False
        char_path = episode_dir / "本次制作角色.md"
        if char_path.exists():
            contains_laoyu = "含捞鱼：是" in char_path.read_text(encoding="utf-8")

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
        "_step_select_categories": "选择分类", "_step_select_price": "选择价格",
        "_step_tips": "配置赞赏", "_step_submit": "提交",
        "_upload_uploader_at": "上传宣传图", "_confirm_crop": "确认裁剪",
        "_select_role": "选择角色", "_upload_tip_images": "上传赞赏图",
        "_upload_tip_by_label": "上传赞赏图", "_upload_uploader_last": "上传赞赏图",
    }

    def __init__(self, config: PublishConfig, session: BrowserSession, progress=None):
        self.config = config
        self.session = session
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

    def publish(self, episode_dir, headless: bool = False) -> dict:
        """发布一弹。返回 ``{success, step, error?, album_name?}``。"""
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

            # 步骤3-5：提交作品 → 表情专辑 → 选静态
            self._report("form", "正在打开提交作品表单…", 0.35)
            self._step_open_submit_form(page)
            # 步骤6：上传表情图（按故事线顺序）
            self._report("upload", f"正在上传 {len(assets.stickers)} 张表情图…", 0.45)
            self._step_upload_stickers(page, assets)
            # 步骤7：填含义词
            self._report("meanings", "正在填写每张表情的含义…", 0.55)
            self._step_fill_meanings(page, assets)
            # 步骤8-9：专辑名 + 介绍
            self._report("album", "正在填写专辑信息…", 0.65)
            self._step_fill_album_info(page, assets)
            # 步骤10：版权
            self._report("copyright", "正在填写版权信息…", 0.70)
            self._step_fill_copyright(page)
            # 步骤11-13：横幅/封面/图标
            self._report("assets", "正在上传横幅/封面/图标…", 0.78)
            self._step_upload_assets(page, assets)
            # 步骤14-18：类型/角色/风格/主题/地区
            self._report("categories", "正在选择专辑分类…", 0.85)
            self._step_select_categories(page, assets)
            # 步骤19：表情价格（免费）
            self._report("price", "正在选择价格（免费）…", 0.90)
            self._step_select_price(page)
            # 步骤20-22：接受赞赏 + 引导语 + 两张赞赏图
            self._report("tips", "正在配置赞赏图…", 0.94)
            self._step_tips(page)
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

        把选择器作为参数传给 JS（避免字符串拼接转义出错）。
        """
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

    # ---- 步骤8-9：专辑名 + 介绍 ----

    def _step_fill_album_info(self, page, assets: EpisodeAssets) -> None:
        """步骤8：专辑名（episode 目录名）；步骤9：介绍（优先 介绍.txt）。"""
        page.fill(S.ALBUM_NAME_INPUT, assets.album_name)
        if assets.intro:
            try:
                page.fill(S.INTRO_TEXTAREA, assets.intro)
            except Exception as e:  # noqa: BLE001
                self._warn(e)

    # ---- 步骤10：版权 ----

    def _step_fill_copyright(self, page) -> None:
        """步骤10：版权信息（固定值，config 可改）。"""
        try:
            page.fill(S.COPYRIGHT_INPUT, self.config.copyright)
        except Exception as e:  # noqa: BLE001
            self._warn(e)

    # ---- 步骤11-13：横幅/封面/图标 ----

    def _step_upload_assets(self, page, assets: EpisodeAssets) -> None:
        """步骤11-13：横幅、封面、图标。

        2026-08 实测：页面改版后 uploader__init 消失；表单上有且仅有 3 个
        可见的 file input，顺序即 横幅/封面/图标（横幅 accept 含 jpeg，
        封面/图标 accept=image/png）。用 JS 打临时 class 后 set_input_files。
        """
        pairs = [("横幅", assets.banner), ("封面", assets.cover), ("图标", assets.icon)]
        for label, img in pairs:
            if img is None:
                self._warn(f"{label}文件缺失，跳过上传（详情页可重新生成）")
                continue
            # 给第 slot 个可见 file input 打临时 class
            ok = page.evaluate("""(label) => {
              const vis = el => !!(el.offsetParent || el.getClientRects().length);
              const files = [...document.querySelectorAll('input[type=file]')].filter(vis);
              // 按标签找槽位：横幅=第一个含 jpeg 的；封面=其后第一个 png；图标=最后一个 png
              let idx = -1;
              if (label === '横幅') {
                idx = files.findIndex(f => (f.accept || '').includes('jpeg') || (f.accept || '').includes('jpg'));
              } else if (label === '封面') {
                const b = files.findIndex(f => (f.accept || '').includes('jpeg') || (f.accept || '').includes('jpg'));
                idx = files.findIndex((f, i) => i > b && (f.accept || '').includes('png'));
              } else {
                for (let i = files.length - 1; i >= 0; i--) {
                  if ((files[i].accept || '').includes('png')) { idx = i; break; }
                }
              }
              if (idx < 0) return false;
              files.forEach(f => f.classList.remove('_asset_target'));
              files[idx].classList.add('_asset_target');
              return true;
            }""", label)
            if not ok:
                self._warn(f"{label}：页面上找不到对应上传控件（可能改版）")
                continue
            try:
                page.set_input_files('._asset_target', str(img))
                page.wait_for_timeout(1500)
                self._confirm_crop(page)
                page.wait_for_timeout(1500)
            except Exception as e:  # noqa: BLE001
                self._warn(e)

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
              if (dt && (dt.innerText || '').includes('未选择')) missing.push('角色/内容');
              return missing;
            }""")
            return list(missing) if isinstance(missing, list) else []
        except Exception:
            return []

    def _confirm_crop(self, page) -> None:
        """uploadFile 后若有"确定"裁剪框，点掉（经验13）。

        2026-08 改版后页面没有裁剪框——超时属正常情况，静默忽略（不再刷警告）。
        """
        try:
            page.click(f'button:has-text("{S.CROP_CONFIRM_TEXT}")', timeout=2000)
        except Exception:  # noqa: BLE001
            pass   # 无裁剪框 = 新版页面正常状态

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
        """步骤15：角色/内容级联下拉。

        含捞鱼→"人物合辑(包含以上多个)"，不含→"女人"。失败不阻塞（提交前平台会校验）。
        """
        try:
            page.click(S.ROLE_DROPDOWN_DT, timeout=3000)
            page.wait_for_timeout(1000)
            # 点 first-level "人物角色"展开二级
            page.click(
                f'.weui-desktop-dropdown__list-ele.first-level:has-text("{S.ROLE_FIRST_LEVEL}")',
                timeout=2000,
            )
            page.wait_for_timeout(1500)
            # 二级菜单选目标（title 包含目标前缀）
            target = S.ROLE_WITH_LAOYU_TITLE if assets.contains_laoyu else S.ROLE_WITHOUT_LAOYU_TITLE
            page.click(f'[title*="{target.split("(")[0]}"]', timeout=2000)
        except Exception as e:  # noqa: BLE001
            self._warn(e)

    # ---- 步骤19：表情价格（免费） ----

    def _step_select_price(self, page) -> None:
        """步骤20：表情价格（免费）——点可见 label，已选跳过。"""
        self._click_label(page, "免费", check=True)

    # ---- 步骤20-22：赞赏 ----

    def _step_tips(self, page) -> None:
        """步骤20：接受赞赏；步骤21：赞赏引导语；步骤22-23：上传两张赞赏图。"""
        # 步骤21：接受赞赏（平台隐藏 checkbox，点 label；已选跳过防取消）
        self._click_label(page, "接受赞赏", check=True)
        # 步骤21：赞赏引导语
        try:
            page.fill(S.TIPS_TEXT_INPUT, self.config.thanks_text, timeout=3000)
        except Exception as e:  # noqa: BLE001
            self._warn(e)
        # 步骤22-23：上传赞赏引导图 + 致谢图
        self._upload_tip_images(page)

    def _upload_tip_images(self, page) -> None:
        """上传赞赏引导图 + 致谢图。

        定位策略（迁移原 skill 方案 A）：逐个 file input 向上找祖先文字，匹配
        "赞赏引导图/引导图" 或 "赞赏致谢图/致谢图"。失败回退：按 uploader__init
        最后两个。上传后处理裁剪框确定（经验13）。
        """
        pairs = [
            (["赞赏引导图", "引导图"], self.config.tip_guide_img),
            (["赞赏致谢图", "致谢图"], self.config.tip_thanks_img),
        ]
        for keywords, img_path in pairs:
            try:
                self._upload_tip_by_label(page, keywords, Path(img_path))
            except Exception:  # noqa: BLE001
                # 回退：最后两个 uploader__init
                self._upload_uploader_last(page, keywords, Path(img_path))

    def _upload_tip_by_label(self, page, keywords, img_path: Path) -> None:
        """按文字标签定位 file input 并上传。"""
        idx = page.evaluate(
            """(kws) => {
                const inputs = document.querySelectorAll('input[type="file"]');
                for (let i = 0; i < inputs.length; i++) {
                    let p = inputs[i];
                    for (let k = 0; k < 8 && p; k++) {
                        const t = (p.innerText || p.textContent || '').trim();
                        if (t && t.length < 120 && kws.some(w => t.includes(w))) {
                            return i;
                        }
                        p = p.parentElement;
                    }
                }
                return -1;
            }""",
            keywords,
        )
        if idx < 0:
            raise RuntimeError(f"未找到含 {keywords} 的 file input")
        file_inputs = page.query_selector_all('input[type="file"]')
        if idx >= len(file_inputs):
            raise RuntimeError(f"file input 索引 {idx} 越界")
        file_inputs[idx].set_input_files(str(img_path))
        page.wait_for_timeout(1500)
        self._confirm_crop(page)
        page.wait_for_timeout(2000)

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
        page.click(
            f'button.weui-desktop-btn_primary:has-text("{S.SUBMIT_BUTTON_TEXT}")'
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
            # 停在表单页：检测平台校验错误 → 明确失败并记录原因
            for err_kw in ("请填写", "必填", "不能为空", "提交失败", "格式不正确", "请完善"):
                if err_kw in body:
                    self._warn(f"平台校验未通过：页面提示含「{err_kw}」，"
                               "可能有必填字段没填上")
                    return False
        return False
