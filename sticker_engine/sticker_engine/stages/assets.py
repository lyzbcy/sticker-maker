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

        # 图标：AI 生成纯头部正面照（P1：平台要求"只含形象头部的正面图像"），
        # codex 失败 fallback 选张（素材永不缺失）
        icon_dir = ctx.episode_dir / "图标"; icon_dir.mkdir(exist_ok=True)
        icon_src = self._make_ai_icon(ctx, paths)
        if icon_src is not None:
            ctx.log(LogEntry(stage="S3", status="OK",
                             message="图标：AI 生成纯头部正面照（50×50）"))
        else:
            icon_src = cover_src
            why = getattr(self, "_icon_last_error", "") or "未知原因"
            ctx.log(LogEntry(stage="S3", status="WARN",
                             message=f"图标：AI 生成失败（{why[:120]}），本次退回复用封面"))
        self._resize_save(icon_src, icon_dir / "图标.png", _ICON_SIZE, _ICON_SIZE)

        # 介绍：1-80 字，硬截断防超限（str() 兜底：write_intro 契约返回 str，
        # 防御 provider 异常返回非 str；真实 VisionProvider 返回 str 时为恒等）
        meanings = [Path(s.path).stem for s in stickers]
        intro = str(self.vision.write_intro(meanings, episode_name=ctx.episode_dir.name))
        intro = intro[:_INTRO_MAX]
        (ctx.episode_dir / "介绍.txt").write_text(intro, encoding="utf-8")

        ctx.log(LogEntry(stage="S3", status="OK",
                         message="横幅/封面/图标/介绍 生成完成"))

    def _make_banner(self, src_paths: list, out: Path) -> None:
        make_banner(src_paths, out)

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
    """前 4 张横向拼成 750×400 宽幅拼贴（横幅）。"""
    cell_w = _BANNER_W // max(len(src_paths), 1)
    banner = Image.new("RGBA", (_BANNER_W, _BANNER_H), (255, 255, 255, 0))
    for i, p in enumerate(src_paths):
        im = Image.open(p).convert("RGBA").resize((cell_w, _BANNER_H), Image.LANCZOS)
        banner.paste(im, (i * cell_w, 0), im)
    banner.save(out)


def resize_save(src: Path, out: Path, w: int, h: int) -> None:
    Image.open(src).convert("RGBA").resize((w, h), Image.LANCZOS).save(out)
