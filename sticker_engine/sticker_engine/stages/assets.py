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

        # 封面：单张最佳图特写（教训14：不复用横幅源）—— 取最具辨识度正面像
        cover_dir = ctx.episode_dir / "封面"; cover_dir.mkdir(exist_ok=True)
        cover_src = self._pick_best_face(paths)
        self._resize_save(cover_src, cover_dir / "封面.png", _COVER_SIZE, _COVER_SIZE)

        # 图标（2026-09-03 降本：用户洞察——成品贴纸本身是大头照风格，
        # 从成品**裁头部**即满足平台"只含形象头部的正面图像"，零生图
        # 消耗——此前 AI 生成每单多烧 1 次生图调用，占单耗 50%。
        # 裁剪失败 → AI 生成兜底 → 再失败 → 封面缩放（降级信号外传））
        icon_dir = ctx.episode_dir / "图标"; icon_dir.mkdir(exist_ok=True)
        icon_src = self._crop_head_icon(paths, icon_dir / "_icon_raw.png")
        if icon_src is not None:
            ctx.log(LogEntry(stage="S3", status="OK",
                             message="图标：成品裁头部（50×50，零生图消耗）"))
        if icon_src is None:
            # 用户纪律（2026-09-03）：绝不为单位图标花生图机会——裁不了
            # 就直接用封面缩放，先上传再说
            pass
        if icon_src is None:
            icon_src = cover_src
            why = getattr(self, "_icon_last_error", "") or "未知原因"
            # 降级信号外传（2026-09-01 批量发布风险）：fallback 产物（格子缩放/
            # 封面缩放形态）曾被平台驳回，run_batch 的自动发布路径据此跳过本单
            ctx.icon_fallback = True
            ctx.log(LogEntry(stage="S3", status="WARN",
                             message=f"图标：AI 生成失败（{why[:120]}），本次退回复用封面"))
        self._resize_save(icon_src, icon_dir / "图标.png", _ICON_SIZE, _ICON_SIZE)

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

    def _crop_head_icon(self, sticker_paths: list, out: Path):
        """从成品贴纸裁头部做图标（2026-09-03 用户降本：绝不为此花生图机会）。

        选片（2026-09-03 驳回修正：曾偏好"看/呆/乖/笑"安静脸——所有专辑
        都挑相似脸导致**跨专辑图标撞图**被平台驳回"不同专辑应使用不一样
        的图片"。改为按 episode 目录名 hash 选格——每单固定但跨单差异化）。
        主体定位两路：
        - 透明底：alpha>8 找主体 bbox
        - 非透明底（ref 库保留背景）：四边采样背景中位色，色差>60 为主体
        裁法（用户口径）：头约占全身 50%——取主体上部 50% 裁方缩 50x50，
        先上传再说。任何失败返回 None 走封面缩放（绝不触发生图）。
        """
        try:
            import numpy as np
            import hashlib
            paths_sorted = sorted(sticker_paths)
            if not paths_sorted:
                return None
            ep_name = Path(paths_sorted[0]).parent.parent.name  # episode 目录名
            h = int(hashlib.md5(ep_name.encode("utf-8")).hexdigest(), 16)
            src = Path(paths_sorted[h % len(paths_sorted)])
            if src is None or not src.exists():
                return None
            im = Image.open(src).convert("RGBA")
            arr = np.asarray(im)
            a = arr[:, :, 3]
            ys = xs = None
            if (a < 8).sum() >= im.width * im.height * 0.05:
                # 透明底：alpha 主体
                ys, xs = np.where(a > 8)
            else:
                # 非透明底：边缘采样背景中位色，色差主体
                edge = np.concatenate([arr[0, :, :3], arr[-1, :, :3],
                                       arr[:, 0, :3], arr[:, -1, :3]]).astype(int)
                bg = np.median(edge, axis=0)
                dist = np.abs(arr[:, :, :3].astype(int) - bg).sum(axis=2)
                ys, xs = np.where(dist > 60)
            if not len(ys):
                return None
            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())
            head_h = max(1, int((y1 - y0) * 0.5))   # 头约占全身 50%（用户口径）
            crop = im.crop((x0, y0, x1 + 1, min(y0 + head_h, y1 + 1)))
            w, h = crop.size
            side = max(w, h)
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            canvas.paste(crop, ((side - w) // 2, (side - h) // 2), crop)
            canvas.resize((50, 50), Image.LANCZOS).save(out)
            return out
        except Exception:
            return None

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

    def _pick_best_face(self, paths: list) -> Path:
        """选最具辨识度的正面像做封面源。

        简化：取第 1 张（真实项目移植 asset_selection.py 的 face_detect，
        按人脸占比/清晰度排序选最佳）。教训14 关键：封面源 ≠ 横幅拼贴源。
        """
        return paths[0]

    def _resize_save(self, src: Path, out: Path, w: int, h: int) -> None:
        resize_save(src, out, w, h)


# ---- 模块级函数：供 AssetsStage 与作品详情页 regen_assets 复用 ----

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
