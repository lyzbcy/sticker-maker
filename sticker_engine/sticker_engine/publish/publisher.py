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

        return cls(
            episode_dir=episode_dir,
            stickers=stickers,
            meanings=meanings,
            album_name=episode_dir.name,
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

    def __init__(self, config: PublishConfig, session: BrowserSession):
        self.config = config
        self.session = session

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

        page = self.session.start(headless=headless)
        try:
            # 步骤1-2：登录（BrowserSession 封装）
            if not self.session.ensure_login(page):
                return {"success": False, "step": "login", "error": "登录失败"}

            # 步骤3-5：提交作品 → 表情专辑 → 选静态
            self._step_open_submit_form(page)
            # 步骤6：上传表情图（按故事线顺序）
            self._step_upload_stickers(page, assets)
            # 步骤7：填含义词
            self._step_fill_meanings(page, assets)
            # 步骤8-9：专辑名 + 介绍
            self._step_fill_album_info(page, assets)
            # 步骤10：版权
            self._step_fill_copyright(page)
            # 步骤11-13：横幅/封面/图标
            self._step_upload_assets(page, assets)
            # 步骤14-18：类型/角色/风格/主题/地区
            self._step_select_categories(page, assets)
            # 步骤19：表情价格（免费）
            self._step_select_price(page)
            # 步骤20-22：接受赞赏 + 引导语 + 两张赞赏图
            self._step_tips(page)
            # 步骤23：提交
            ok = self._step_submit(page)
            if not ok:
                return {"success": False, "step": "submit",
                        "error": "未检测到提交成功标志", "album_name": assets.album_name}
            return {"success": True, "step": "done",
                    "album_name": assets.album_name}
        except Exception as e:  # noqa: BLE001 - 保现场
            try:
                page.screenshot(path=str(assets.episode_dir / "_publish_error.png"))
            except Exception:  # noqa: BLE001
                pass
            return {"success": False, "step": "unknown",
                    "error": f"{type(e).__name__}: {e}"}
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
        # 步骤5：选静态（点 radio icon；可能默认已选，失败忽略）
        try:
            page.click(S.STATIC_RADIO, timeout=3000)
        except Exception:  # noqa: BLE001
            pass

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
            except Exception:  # noqa: BLE001
                pass

    # ---- 步骤10：版权 ----

    def _step_fill_copyright(self, page) -> None:
        """步骤10：版权信息（固定值，config 可改）。"""
        try:
            page.fill(S.COPYRIGHT_INPUT, self.config.copyright)
        except Exception:  # noqa: BLE001
            pass

    # ---- 步骤11-13：横幅/封面/图标 ----

    def _step_upload_assets(self, page, assets: EpisodeAssets) -> None:
        """步骤11-13：横幅、封面、图标。

        横幅/封面走 uploader__init（有裁剪框，经验13 点确定）；图标用
        accept=image/png 的 file input（步骤6 经验：图标 input 是第 4 个）。
        """
        # 横幅
        if assets.banner is not None:
            self._upload_uploader_at(page, 0, assets.banner)
        # 封面
        if assets.cover is not None:
            self._upload_uploader_at(page, 1, assets.cover)
        # 图标：用 accept=image/png 的 file input
        if assets.icon is not None:
            png_inputs = page.query_selector_all('input[type="file"][accept="image/png"]')
            if png_inputs:
                try:
                    png_inputs[0].set_input_files(str(assets.icon))
                    page.wait_for_timeout(2000)
                except Exception:  # noqa: BLE001
                    pass

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
        except Exception:  # noqa: BLE001
            pass
        # 经验13：uploadFile 后若有裁剪框，点确定
        self._confirm_crop(page)
        page.wait_for_timeout(2000)

    def _confirm_crop(self, page) -> None:
        """uploadFile 后若有"确定"裁剪框，点掉（经验13）。"""
        try:
            page.click(f'button:has-text("{S.CROP_CONFIRM_TEXT}")', timeout=2000)
        except Exception:  # noqa: BLE001
            pass  # 无裁剪框，忽略

    # ---- 步骤14-18：类型/角色/风格/主题/地区 ----

    def _step_select_categories(self, page, assets: EpisodeAssets) -> None:
        """步骤14：类型细分；步骤15：角色/内容级联；步骤16：风格；步骤17：主题；步骤18：地区。"""
        # 步骤14：类型细分（卡通表情/其他，value=1）
        try:
            page.click(f'input[type="radio"][value="{S.CATEGORY_RADIO_VALUE}"]', timeout=3000)
        except Exception:  # noqa: BLE001
            pass
        # 步骤15：角色/内容级联下拉（含捞鱼→人物合辑，不含→女人）
        self._select_role(page, assets)
        # 步骤16：风格（软萌可爱 + 日常）
        for sel in (S.STYLE_CHECKBOX_SOFT, S.STYLE_CHECKBOX_DAILY):
            try:
                page.click(sel, timeout=3000)
            except Exception:  # noqa: BLE001
                pass
        # 步骤17：主题（万能通用）
        try:
            page.click(f'input[type="radio"][value="{S.THEME_RADIO_VALUE}"]', timeout=3000)
        except Exception:  # noqa: BLE001
            pass
        # 步骤18：地区（全球 DEF）
        try:
            page.click(f'input[type="radio"][value="{S.REGION_RADIO_VALUE}"]', timeout=3000)
        except Exception:  # noqa: BLE001
            pass

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
        except Exception:  # noqa: BLE001
            pass

    # ---- 步骤19：表情价格（免费） ----

    def _step_select_price(self, page) -> None:
        """步骤19：表情价格（免费）。

        原 skill：找 value="true" 的 radio 且 label 含"免费"。
        """
        try:
            page.click(
                f'label:has-text("免费") input[type="radio"][value="{S.PRICE_FREE_RADIO_VALUE}"]',
                timeout=3000,
            )
        except Exception:  # noqa: BLE001
            # 回退：直接 value="true"
            try:
                page.click(f'input[type="radio"][value="{S.PRICE_FREE_RADIO_VALUE}"]', timeout=2000)
            except Exception:  # noqa: BLE001
                pass

    # ---- 步骤20-22：赞赏 ----

    def _step_tips(self, page) -> None:
        """步骤20：接受赞赏；步骤21：赞赏引导语；步骤22-23：上传两张赞赏图。"""
        # 步骤20：接受赞赏（勾选 label 含"接受赞赏"的 checkbox）
        try:
            page.click(f'label:has-text("接受赞赏") input[type="checkbox"]', timeout=3000)
        except Exception:  # noqa: BLE001
            pass
        # 步骤21：赞赏引导语
        try:
            page.fill(S.TIPS_TEXT_INPUT, self.config.thanks_text, timeout=3000)
        except Exception:  # noqa: BLE001
            pass
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
        """步骤23：点提交，等待成功标志。

        成功标志（迁移原 skill）：页面文案含"提交成功"或"审核中"，或 URL 离开
        表单页。返回是否检测到成功。
        """
        page.click(
            f'button.weui-desktop-btn_primary:has-text("{S.SUBMIT_BUTTON_TEXT}")'
        )
        page.wait_for_timeout(5000)
        # 检测成功
        try:
            body = page.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            body = ""
        if "提交成功" in body or "审核中" in body:
            return True
        # URL 离开表单页也算成功（跳转到管理页）
        url = page.url
        if "login" not in url and "readtemplate" not in url:
            # 粗判：不再在提交表单上
            return True
        return False
