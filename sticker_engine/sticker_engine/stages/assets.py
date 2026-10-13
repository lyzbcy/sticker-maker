"""S3 素材生成阶段：横幅 750×400 / 封面 240×240 / 图标 50×50 / 介绍.txt。

**教训14（封面 ≠ 横幅源）**：封面应是单角色特写（最具辨识度的正面像），
横幅是横向宽幅拼贴。两者源图不同——横幅取前 4 张拼贴，封面取 `_pick_best_face`
（简化：第 1 张；真实项目移植 asset_selection.py 的 face_detect 选最大脸）。

移植自现有 make_assets.py，适配 sticker_engine 的 stage/provider 框架。
"""
from pathlib import Path

from PIL import Image

from ..pipeline.context import PipelineContext, LogEntry
from ..providers.vision import VisionProvider
from .generate import HEADER_EMOS

# HEADER_EMOS 的含义词集合（封面/图标选格的词表信号，与 generate 同源）
_HEADER_EMOS_ZH = frozenset(emo[2] for emo in HEADER_EMOS)
# 撞名后缀（generate._random_combo_panels 的 dedup 规则）：场景格先占
# "心动了"，header 格被改名"心动了～"——匹配时容忍单个尾缀
_HEADER_DEDUP_SUFFIXES = ("哦", "呀", "～")


def _match_header_word(zh: str) -> bool:
    """含义词是否 header 格词（精确 + 单尾缀变体）。"""
    zh = zh.strip()
    if zh in _HEADER_EMOS_ZH:
        return True
    if len(zh) >= 2 and zh[-1] in _HEADER_DEDUP_SUFFIXES:
        return zh[:-1] in _HEADER_EMOS_ZH
    return False

# 微信平台素材目标尺寸（spec）
_BANNER_W, _BANNER_H = 750, 400
_COVER_SIZE = 240
_ICON_SIZE = 50
_INTRO_MAX = 80   # 微信介绍 80 字硬限制

# P1（平台驳回整改，doc/reference/platform-review.md）：平台硬规则"图标 =
# 只含形象头部的正面图像"，格子缩放永远不合规 → 单独生成一张大头照。
# codex 铁律：单行 prompt（多行经 codex.cmd 丢参考图）；refs 传 base 保 IP。
_ICON_AI_PROMPT = (
    "Generate ONE single square sticker image: ONLY the character's HEAD, "
    "front-facing, perfectly centered, filling about 80% of the frame, "
    "gentle happy expression, eyes open, thick white outline around the head, "
    "flat solid magenta background (#ff00ff), no text, no letters, no props, "
    "no accessories beyond what is on the head, no border, no frame. "
    "Copy the character design EXACTLY from the attached reference image."
)

# ---- 封面大头照改造（2026-09-08，驳回数据驱动的 P0）----
# 平台驳回复盘（82 单 meta.json）：66+ 单被"图标/头部正面像"驳回；
# 而封面此前 = 第 1 张成品直接缩放（全身像头部仅占画幅 ~25%），与官方
# "封面 = 正面半身像"规范不符。生成端已固定 keyword_combo 单尾部 4 格
# 为 HEAD SHOT（generate.HEADER_SLOTS，实测头部占比 70%+）——封面直接
# 复用这个洞：选 header 格 → alpha-bbox zoom-in 裁剪 → 形态质检。
# 0 token、零新依赖（不用 OpenCV/人脸模型：透明底 alpha 通道就是
# 100% 准确的主体检测器，见 doc/reference/platform-review.md）。
#
# 裁剪定位（2026-09-08 二版，离线实验+老单回归驱动）：
# header 格主体 bbox 已占原图 93-99%（几乎满格），放不大、要反向
# zoom-in。固定 zoom 会切脸（"头发占满 bbox"的格 head 比例失真），
# 故用 mask 行宽剖面自适应找肩线（_head_bottom_y，纯 numpy 无模型），
# 窗口 = 头顶到肩线高度 / 目标占比；剖面失真回退固定 head 比例。
# 回归对比图（temp/cover_exp/cmp_*.png）目测验收：294 头部画幅 ~78%。
_COVER_HEAD_RATIO = 0.60    # 兜底：头部占 bbox 高度比例（chibi 头肩格经验值）
_COVER_TARGET = 0.78        # 裁剪后头部目标画幅占比（>平台 75% 线）
# 形态质检：合格 header 格 bbox 宽/高接近方形（实测 0.93-0.99）；
# 全身像 w/h ≈ 0.5-0.6，低于阈值说明选到场景格 → 换格/回退
_COVER_MIN_BBOX_RATIO = 0.65


class AssetsStage:
    """S3：横幅 750×400 / 封面 240×240 / 图标 50×50 / 介绍.txt。"""

    def __init__(self, vision: VisionProvider):
        self.vision = vision

    def run(self, ctx: PipelineContext) -> None:
        stickers = ctx.stickers
        if not stickers:
            ctx.log(LogEntry(stage="S3", status="FAIL", message="无成品图，跳过素材生成"))
            return
        paths = [Path(s.path) for s in stickers]

        # 横幅：取前 4 张横向拼贴（750×400）
        banner_dir = ctx.episode_dir / "横幅"; banner_dir.mkdir(exist_ok=True)
        self._make_banner(paths[:4], banner_dir / "横幅.png")

        # 封面（2026-09-08 大头照改造）：header 特写格 + zoom-in 裁剪，
        # 保证头部占画幅 ≥75%（此前 = 第 1 张直接缩放，全身像头部仅
        # ~25%，与平台"封面 = 正面半身像"规范不符）。失败回退旧行为
        # 并外传 cover_fallback（批量自动发布据此跳过，同 icon_fallback）。
        cover_dir = ctx.episode_dir / "封面"; cover_dir.mkdir(exist_ok=True)
        cover_src = self._pick_best_face(paths, ctx)
        cover_ok = False
        if cover_src is not None:
            cover_ok = make_big_head_cover(cover_src, cover_dir / "封面.png")
        if cover_ok:
            ctx.log(LogEntry(stage="S3", status="OK",
                             message=f"封面：header 格大头照（{cover_src.name}，"
                                     f"头部画幅≈{_COVER_TARGET:.0%}）"))
        else:
            cover_src = paths[0]   # 教训14 关键：回退不复用横幅源
            # 降级分两档（2026-09-08）：combo 单 header 格翻车 → 外传
            # cover_fallback（批量自动发布跳过，同 icon_fallback）；
            # 非 combo 单（本就无 header 格，旧行为即第 1 张缩放且封面
            # 无被拒记录）→ 只 WARN 不拦截，不影响存量模式产量。
            if getattr(self, "_cover_had_header", False):
                ctx.cover_fallback = True
                why = getattr(self, "_cover_last_error", "") or "header 格裁剪失败"
                ctx.log(LogEntry(stage="S3", status="WARN",
                                 message=f"封面：header 格大头照失败（{why[:120]}），"
                                         "回退第 1 张缩放（易被驳回，已跳过自动发布）"))
            else:
                ctx.log(LogEntry(stage="S3", status="WARN",
                                 message="封面：非 combo 单无 header 格，"
                                         "按旧规则取第 1 张缩放"))
            self._resize_save(cover_src, cover_dir / "封面.png", _COVER_SIZE, _COVER_SIZE)

        # 图标（2026-09-09 用户定稿：图标 = 封面同图直接缩 50×50）。
        # 此前独立从成品格裁头部（_crop_head_icon），但选格构图不稳定，
        # 用户实测"封面选得好、图标选得不好"——封面已是肩线构图大头照
        # （头部画幅 ≥78%），同图缩 50×50 构图天然一致且清晰。
        # 图标无独立降级：封面成功则图标必然成功；封面降级由
        # cover_fallback 携带（批量自动发布据此跳过）。
        icon_dir = ctx.episode_dir / "图标"; icon_dir.mkdir(exist_ok=True)
        self._resize_save(cover_dir / "封面.png", icon_dir / "图标.png",
                          _ICON_SIZE, _ICON_SIZE)
        ctx.log(LogEntry(stage="S3", status="OK",
                         message="图标：与封面同图（50×50 缩放）"))

        # 赞赏引导图/致谢图（69 驳回：默认情侣图与专辑形象无关被拒）——
        # 用本组贴纸派生：柔和底色 + 角色贴纸 + 一行引导语，与形象强相关
        tip_dir = ctx.episode_dir / "赞赏图"; tip_dir.mkdir(exist_ok=True)
        try:
            self._make_tip_images(paths, cover_src, tip_dir)
            ctx.log(LogEntry(stage="S3", status="OK",
                             message="赞赏图：已用本组角色生成引导图/致谢图"))
        except Exception as e:   # noqa: BLE001
            ctx.log(LogEntry(stage="S3", status="WARN",
                             message=f"赞赏图生成失败（{type(e).__name__}: {e}），发布时用默认图"))

        # 介绍：1-80 字，硬截断防超限（str() 兜底：write_intro 契约返回 str，
        # 防御 provider 异常返回非 str；真实 VisionProvider 返回 str 时为恒等）
        meanings = [Path(s.path).stem for s in stickers]
        # 0 token 模式（2026-09-03）：介绍文案纯文本调用也耗 token——
        # 默认走本地模板（基于含义词），prefs.vision_calls=True 才用 AI
        if bool(getattr(ctx.config.prefs, "vision_calls", False)):
            intro = str(self.vision.write_intro(meanings, episode_name=ctx.episode_dir.name))
        else:
            intro = make_local_intro(ctx.episode_dir.name, meanings)
        intro = intro[:_INTRO_MAX]
        (ctx.episode_dir / "介绍.txt").write_text(intro, encoding="utf-8")

        ctx.log(LogEntry(stage="S3", status="OK",
                         message="横幅/封面/图标/介绍 生成完成"))

    def _make_tip_images(self, sticker_paths: list, cover_src: Path, out_dir: Path) -> None:
        """生成本组角色专属的赞赏引导图(939×701)/致谢图(939×939)。

        布局：柔和奶油底 + 角色贴纸（透明底成品放大居中）+ 一行手写感引导语。
        与专辑形象强相关（平台驳回整改：默认情侣图相关度不够）。
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        from PIL import ImageDraw, ImageFont
        src = Image.open(cover_src).convert("RGBA")
        # 拿一张透明底贴纸做主视觉（封面源可能是 JPEG 白底，优先找透明成品）
        main = None
        for p in sticker_paths:
            im = Image.open(p).convert("RGBA")
            if im.getpixel((3, 3))[3] == 0:
                main = im
                break
        if main is None:
            main = src
        guide_out = out_dir / "赞赏引导图.png"
        thanks_out = out_dir / "赞赏致谢图.png"
        font = None
        for fp in [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
                   r"C:\Windows\Fonts\simhei.ttf"]:
            if Path(fp).exists():
                font = ImageFont.truetype(fp, 44)
                break

        def _compose(size, text):
            # R4（评审）：底色用纯白——非透明封面（白底 JPEG）贴上来无边界；
            # 透明贴纸在白底上同样干净
            canvas = Image.new("RGBA", size, (255, 255, 255, 255))
            d = ImageDraw.Draw(canvas)
            # 顶部/底部粉色饰带（保留一点赞赏卡的暖感）
            d.rectangle([0, 0, size[0], 26], fill=(255, 214, 214, 255))
            d.rectangle([0, size[1] - 26, size[0], size[1]], fill=(255, 214, 214, 255))
            # 角色贴纸放大居中（等比，占高 ~70%）
            target_h = int(size[1] * 0.70)
            scale = target_h / main.height
            sticker = main.resize((int(main.width * scale), target_h), Image.LANCZOS)
            canvas.paste(sticker, ((size[0] - sticker.width) // 2,
                                   (size[1] - sticker.height) // 2 - 14), sticker)
            if font is not None:
                bbox = d.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                d.text(((size[0] - tw) // 2, size[1] - 96), text,
                       font=font, fill=(214, 106, 106, 255))
            return canvas.convert("RGB")

        _compose((939, 701), "喜欢的话，请赏一杯奶茶吧～").save(guide_out)
        # 2026-09-01：❤ 在 msyh 无字形渲染成"豆腐块"（58 赞赏图实测），
        # 平台上就是乱码方块 → 换用字体保证有的全角符号
        _compose((939, 939), "谢谢你的赞赏，比心～").save(thanks_out)

    def _make_banner(self, src_paths: list, out: Path) -> None:
        make_banner(src_paths, out)

    # _crop_head_icon 已删（2026-09-09 用户定稿：图标 = 封面同图缩放，
    # 独立裁头部构图不稳定；见 run() 图标段注释）

    def _make_ai_icon(self, ctx: PipelineContext, fallback_paths: list):
        """AI 生成图标专属"纯头部正面照"，返回成品路径；失败返回 None。

        - refs 用 S0 选中的 base（IP 与整单一致）；无 base 传第 1 张成品
        - codex 铁律遵守：_ICON_AI_PROMPT 单行、refs 在 ASCII 暂存由 provider 处理
        - 生成后抠洋红底 + trim 残留 + 补方 240，存 图标/_icon_raw.png
        - 生成失败/图异常（纯色废图）→ None（调用方 fallback）
        """
        codex = getattr(self.vision, "codex", None)
        if codex is None:
            return None
        # R4（评审）：只传第 1 张 base——多 base 时 codex 可能画拼贴/混角色
        refs = list(getattr(ctx, "selected_bases", []) or [])[:1]
        if not refs and fallback_paths:
            refs = [fallback_paths[0]]
        if not refs:
            return None
        import time as _time
        t0 = _time.time()
        try:
            raw = codex.generate(prompt=_ICON_AI_PROMPT, refs=refs)
        except Exception as e:   # noqa: BLE001
            self._icon_last_error = f"{type(e).__name__}: {e}"
            return None
        self._icon_last_error = str(getattr(codex, "last_error", "") or "")
        if not raw or not Path(raw).exists():
            return None
        # R2（评审）：新鲜度校验——codex 正常退出但没画新图时，provider 会
        # 返回 output_dir 里任意"最新"图（可能是 S1 的 4x4 网格）→ 50px
        # 图标变微型宫格，恰是驳回形态。只认本次调用之后落盘的图。
        try:
            if Path(raw).stat().st_mtime < t0 - 2:
                return None
        except OSError:
            return None
        try:
            from PIL import Image as _Im
            img = _Im.open(raw).convert("RGBA")
            # 废图质检：>98% 同灰度 = 纯色废图（generate 阶段同款判据）
            hist = img.convert("L").histogram()
            if max(hist) / (img.width * img.height) > 0.98:
                return None
            # 抠洋红 + trim 残留带 + 补方（与 S2 同套路，模块级函数复用）
            try:
                from ..providers.chromakey import ChromaKeyProvider
                ck = getattr(self, "_icon_chromakey", None)
                if ck is None:
                    ck = self._icon_chromakey = ChromaKeyProvider()
                img = ck.remove_key_auto(img)
            except Exception:
                pass
            from .postprocess import (remove_edge_background, trim_border_band,
                                      ensure_size)
            img = remove_edge_background(img)
            img = trim_border_band(img)
            img = ensure_size(img)
            out = ctx.episode_dir / "图标" / "_icon_raw.png"
            out.parent.mkdir(exist_ok=True)
            img.save(out)
            return out
        except Exception:
            return None

    def _pick_best_face(self, paths: list, ctx: PipelineContext = None):
        """选封面源（2026-09-08 重写：header 特写格优先）。

        选格信号（pick_header_candidates：ctx.header_slots → 词表命中 →
        meaning_map 尾部 4 格），候选做 bbox 形态质检（w/h ≥ 0.65 即
        头肩方格）逐个尝试，全灭返回 None（调用方回退旧行为）。
        教训14 关键：封面源 ≠ 横幅拼贴源。
        """
        try:
            if not paths:
                self._cover_had_header = False
                return None
            header_slots = list(getattr(ctx, "header_slots", None) or []) \
                if ctx is not None else []
            meaning_map = dict(getattr(ctx, "meaning_map", None) or {}) \
                if ctx is not None else {}
            cands = pick_header_candidates(paths, header_slots=header_slots,
                                           meaning_map=meaning_map,
                                           ep_dir=Path(paths[0]).parent.parent)
            if not cands:
                self._cover_last_error = "无 header 特写格（非 combo 单或含义词缺失）"
                self._cover_had_header = False
                return None
            self._cover_had_header = True
            for cand in cands:
                if cand.exists() and _is_head_shot(cand):
                    return cand
            self._cover_last_error = "header 格形态质检全不过"
            return None
        except Exception as e:   # noqa: BLE001
            self._cover_last_error = f"{type(e).__name__}: {e}"
            self._cover_had_header = False
            return None

    def _resize_save(self, src: Path, out: Path, w: int, h: int) -> None:
        resize_save(src, out, w, h)


# ---- 模块级函数：供 AssetsStage 与作品详情页 regen_assets 复用 ----

def pick_header_candidates(paths: list, header_slots=None, meaning_map=None,
                           ep_dir: Path = None) -> list:
    """返回 header 特写格候选路径（hash 轮转排序，失败可顺延下一格）。

    两套定位方式（2026-09-08 回归修正）：
    1. header_slots（ctx 运行时）——paths 即 panel 序，按 slots 位置索引。
    2. meaning_map 词表命中（regen 等）——**词→同名文件反查**，绝不能拿
       panel 序号去索引文件名排序后的列表：中文字典序 ≠ panel 序，正是
       68 号单错位事故的同款约定（cli._episode_stickers 注释）。
       兼容撞名后缀（"心动了～"），反查不到同名文件时放弃该词。
    无 header 信号（老单/非 combo 单）返回空列表，调用方走回退。
    """
    import hashlib
    import json
    mm = dict(meaning_map or {})
    if not mm and ep_dir is not None:
        try:
            f = Path(ep_dir) / "meaning_map.json"
            if f.exists():
                mm = {int(k): str(v) for k, v
                      in json.loads(f.read_text(encoding="utf-8")).items()}
        except Exception:   # noqa: BLE001
            mm = {}
    if header_slots:
        slots = [s for s in (int(s) for s in header_slots)
                 if 1 <= s <= len(paths)]
        if not slots:
            return []
        ep_name = Path(paths[0]).parent.parent.name
        h = int(hashlib.md5(ep_name.encode("utf-8")).hexdigest(), 16)
        start = h % len(slots)
        ordered = slots[start:] + slots[:start]
        return [Path(paths[s - 1]) for s in ordered]

    words = [v for v in (mm.get(k) for k in sorted(mm, key=int))
             if _match_header_word(str(v))]
    if not words:
        return []
    final = (Path(ep_dir) if ep_dir is not None
             else Path(paths[0]).parent.parent) / "最终版"
    cands = [final / f"{w.strip()}.png" for w in words]
    cands = [c for c in cands if c.exists()]
    if len(cands) < 2:
        return _prefer_noword(cands)
    ep_name = final.parent.name
    h = int(hashlib.md5(ep_name.encode("utf-8")).hexdigest(), 16)
    start = h % len(cands)
    ordered = cands[start:] + cands[:start]
    return _prefer_noword(ordered)


def _prefer_noword(cands: list) -> list:
    """solid 配字单：封面/图标必须无字（平台对图标明文"去除文字信息"），
    S2 已把无字版存 原图/_noword/同名.png——存在即替换为无字源。"""
    out = []
    for p in cands:
        p = Path(p)
        noword = p.parent.parent / "原图" / "_noword" / p.name
        out.append(noword if noword.exists() else p)
    return out


def _body_mask(src_path: Path):
    """主体 mask：透明底走 alpha（>8），非透明底走边缘中位色差（>60），
    scipy 连通域过滤小噪声（保留最大域 + 面积 ≥5% 的域，防飘丝/小
    doodle 撑大 bbox）。返回 (mask, im)；失败返回 None。
    （scipy 为引擎既有依赖）"""
    import numpy as np
    from scipy import ndimage
    im = Image.open(src_path).convert("RGBA")
    arr = np.asarray(im)
    a = arr[:, :, 3]
    if (a < 8).sum() >= im.width * im.height * 0.05:
        mask = a > 8
    else:
        edge = np.concatenate([arr[0, :, :3], arr[-1, :, :3],
                               arr[:, 0, :3], arr[:, -1, :3]]).astype(int)
        bg = np.median(edge, axis=0)
        dist = np.abs(arr[:, :, :3].astype(int) - bg).sum(axis=2)
        mask = dist > 60
    lab, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        big = sizes.max()
        keep = np.zeros_like(mask)
        for i, s in enumerate(sizes, 1):
            if s >= big * 0.05:
                keep |= (lab == i)
        mask = keep
    return mask, im


def _body_bbox(src_path: Path):
    """主体 bbox + mask + im（供裁剪/质检共用）。失败返回 None。"""
    got = _body_mask(src_path)
    if got is None:
        return None
    mask, im = got
    import numpy as np
    ys, xs = np.where(mask)
    if not len(ys):
        return None
    return (int(xs.min()), int(ys.min()),
            int(xs.max()) + 1, int(ys.max()) + 1), im, mask


def _head_bottom_y(mask, x0, y0, x1, y1):
    """mask 行宽剖面找头部底界（肩线）：从 bbox 顶往下，最宽行（脸/发）
    之后的骤减点（< 峰值 62%）即脖颈。找不到骤减（长发贴身/剖面失真）
    返回 None，调用方回退固定比例。纯 numpy，无模型依赖。"""
    import numpy as np
    widths = mask[y0:y1, x0:x1].sum(axis=1).astype(float)
    if widths.size < 12:
        return None
    k = np.ones(5) / 5.0
    sm = np.convolve(widths, k, mode="same")
    peak_i = int(sm.argmax())
    peak = sm[peak_i]
    if peak <= 0:
        return None
    drop = np.where(sm[peak_i:] < peak * 0.62)[0]
    if not drop.size:
        return None
    return y0 + peak_i + int(drop[0])


def _is_head_shot(src_path: Path, min_ratio: float = _COVER_MIN_BBOX_RATIO) -> bool:
    """header 格形态质检：主体 bbox 宽/高 ≥ min_ratio（头肩像近方格）。
    全身站立像 w/h ≈ 0.5-0.6 不达标——防误把场景格当头肩格裁。"""
    try:
        got = _body_bbox(src_path)
        if got is None:
            return False
        (x0, y0, x1, y1), _im, _mask = got
        w, h = x1 - x0, y1 - y0
        return h > 0 and (w / h) >= min_ratio
    except Exception:   # noqa: BLE001
        return False


def make_big_head_cover(src: Path, out: Path, size: int = _COVER_SIZE) -> bool:
    """封面大头照：header 特写格 → 自适应方形窗口 zoom-in → 240×240 透明 PNG。

    窗口定位（2026-09-08 二版）：先用 mask 行宽剖面找肩线（头部底界），
    窗口边长 = 头顶到肩线高度 / 目标占比，使头部占画幅 78%（> 平台 75%
    线）；剖面失真（长发贴身找不到骤减点/骤减点过低）回退固定比例
    head=bbox_h×60%。锚点 x 居中、y 从 bbox 顶开始（保头发完整、切下
    部身体）。任何失败返回 False（调用方回退旧行为），绝不抛异常。
    """
    try:
        got = _body_bbox(Path(src))
        if got is None:
            return False
        (x0, y0, x1, y1), im, mask = got
        bw, bh = x1 - x0, y1 - y0
        if bh <= 0:
            return False
        neck = _head_bottom_y(mask, x0, y0, x1, y1)
        head_h = (neck - y0) if neck else 0
        if not (bh * 0.35 <= head_h <= bh * 0.75):
            # 肩线过高（半张脸）/过低（profile 失真）→ 固定比例兜底
            head_h = bh * _COVER_HEAD_RATIO
        side = int(min(max(head_h / _COVER_TARGET, bh * 0.5),
                       min(bh * 1.2, min(im.width, im.height))))
        cx = (x0 + x1) // 2
        wx0 = max(0, min(cx - side // 2, im.width - side))
        wy0 = max(0, min(y0, im.height - side))
        win = im.crop((wx0, wy0, min(wx0 + side, im.width),
                       min(wy0 + side, im.height)))
        scale = size / side
        nw, nh = max(1, round(win.width * scale)), max(1, round(win.height * scale))
        win = win.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(win, ((size - nw) // 2, (size - nh) // 2), win)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out)
        return True
    except Exception:   # noqa: BLE001
        return False


def make_banner(src_paths: list, out: Path) -> None:
    """前 4 张成品拼 750×400 横幅（2026-09-02 美观度重做，评分复盘驱动）。

    旧版看图复盘（低分 84/77/69 与高分 86/80/import 单横幅共性一致）：
    240×240 方图被硬拉成 187×400（纵向压扁变形）+ 全透明底，预览黑底
    下就是"4 张变形截图拼接"，零氛围感——横幅难看与单子分数无关，
    是生成方案本身的问题。新版：
    - 奶油粉渐变实底 + 波点/小爱心点缀（萌系氛围，不再透明底）
    - 每张贴纸等比缩放（不变形）放进白色圆角卡片，卡片带柔和投影
    - 等距排布 + 轻微上下错落，整体居中，留白均匀
    """
    from PIL import ImageDraw, ImageFilter
    import random as _random

    paths = [Path(p) for p in src_paths[:4]]
    n = max(len(paths), 1)

    # 1) 奶油粉纵向渐变实底
    top_rgb, bot_rgb = (255, 247, 250), (255, 226, 236)
    banner = Image.new("RGBA", (_BANNER_W, _BANNER_H))
    for y in range(_BANNER_H):
        t = y / max(_BANNER_H - 1, 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(top_rgb, bot_rgb))
        ImageDraw.Draw(banner).line([(0, y), (_BANNER_W, y)], fill=row + (255,))

    # 2) 波点 + 小爱心点缀（固定种子可复现，避开中心贴纸区也无妨——卡片会盖住）
    rng = _random.Random(20260902)
    d = ImageDraw.Draw(banner)
    for _ in range(26):
        x, y = rng.randrange(8, _BANNER_W - 8), rng.randrange(8, _BANNER_H - 8)
        r = rng.randrange(3, 7)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 208, 224, 110))
    for _ in range(8):   # 极简小爱心（两圆+三角）
        x, y = rng.randrange(20, _BANNER_W - 20), rng.randrange(20, _BANNER_H - 20)
        s = rng.randrange(4, 7)
        d.ellipse([x - s, y - s, x, y], fill=(255, 172, 193, 130))
        d.ellipse([x, y - s, x + s, y], fill=(255, 172, 193, 130))
        d.polygon([(x - s, y - s // 3), (x + s, y - s // 3), (x, y + s)],
                  fill=(255, 172, 193, 130))

    # 3) 白色圆角卡片（带柔和投影）+ 等比贴纸
    # 两层循环：先把所有投影合成完，再画所有卡片——避免后画卡片的
    # 投影叠到先画好的卡片上形成"错位深缝"（视觉复检发现）
    margin_x, gap = 30, 18
    card_w = (_BANNER_W - 2 * margin_x - (n - 1) * gap) // n
    card_h = min(int(card_w * 1.35), 240)
    base_y = (_BANNER_H - card_h) // 2 - 6
    cards = []
    for i, p in enumerate(paths):
        cx = margin_x + i * (card_w + gap)
        # 轻微上下错落（第 0/2 张略升，1/3 张略降），打破机械一排
        cy = base_y + (8 if i % 2 else -8)
        cards.append((cx, cy, p))
    shadow = Image.new("RGBA", (_BANNER_W, _BANNER_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for cx, cy, _p in cards:
        sd.rounded_rectangle(
            [cx, cy + 5, cx + card_w, cy + card_h + 5], radius=22,
            fill=(120, 80, 90, 60))
    banner = Image.alpha_composite(banner, shadow.filter(
        ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(banner)
    for cx, cy, p in cards:
        d.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=22,
                            fill=(255, 255, 255, 242))
        # 贴纸等比缩放进卡片内边距，不变形
        try:
            im = Image.open(p).convert("RGBA")
        except OSError:
            continue
        pad = 14
        im.thumbnail((card_w - 2 * pad, card_h - 2 * pad), Image.LANCZOS)
        banner.paste(im, (cx + (card_w - im.width) // 2,
                          cy + (card_h - im.height) // 2), im)

    banner.convert("RGB").save(out)


def resize_save(src: Path, out: Path, w: int, h: int) -> None:
    Image.open(src).convert("RGBA").resize((w, h), Image.LANCZOS).save(out)


def make_local_intro(album_name: str, meanings: list) -> str:
    """0 token 本地介绍模板（2026-09-04 抽出可复用：S3 先用目录名占位，
    系列编号命名后用最终专辑名重写——此前介绍里的《》是 episode 目录名，
    156-160 五单全部带《episode_20260903_xxx》上平台）。"""
    names = [m for m in (meanings or []) if m][:4]
    base = (f"《{album_name}》：{'、'.join(names)}，软萌日常表情。"
            if names else f"《{album_name}》软萌日常表情包。")
    return base[:_INTRO_MAX]


def rewrite_intro_with_album(episode_dir: Path, album_name: str) -> str:
    """系列命名后重写介绍（cmd_run/engine.run 成功路径调用）。"""
    mm = episode_dir / "meaning_map.json"
    meanings = []
    if mm.exists():
        try:
            import json
            data = json.loads(mm.read_text(encoding="utf-8"))
            meanings = [str(v) for _, v in sorted(data.items(), key=lambda kv: int(kv[0]))]
        except Exception:   # noqa: BLE001
            meanings = []
    intro = make_local_intro(album_name, meanings)
    (episode_dir / "介绍.txt").write_text(intro, encoding="utf-8")
    return intro
